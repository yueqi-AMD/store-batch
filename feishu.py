"""Feishu Bitable API client (tenant token) for the store-batch pipeline.

All access targets the base/table configured in config.json. An optional
allowlist (config.security.allowed_app_token / allowed_table_id) can lock
the pipeline to a single table.
"""
import json
import os
import time
from pathlib import Path

import requests

BASE = "https://open.feishu.cn/open-apis"


class FeishuError(RuntimeError):
    pass


class Feishu:
    def __init__(self, app_token: str, table_id: str, allowlist=None):
        """allowlist: 可选的 (app_token, table_id) 白名单；配置后只允许操作该表。"""
        if allowlist and (app_token, table_id) != tuple(allowlist):
            raise FeishuError(
                "blocked: this pipeline is configured to only touch "
                f"{allowlist[0]}/{allowlist[1]}, got {app_token}/{table_id}"
            )
        self.app_id = os.environ.get("LARK_APP_ID")
        self.app_secret = os.environ.get("LARK_APP_SECRET")
        if not self.app_id or not self.app_secret:
            raise FeishuError("LARK_APP_ID / LARK_APP_SECRET not set in environment")
        self.app_token = app_token
        self.table_id = table_id
        self._token = None
        self._token_expire = 0.0
        self.s = requests.Session()

    # ------------------------------------------------------------------ auth
    def token(self) -> str:
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        r = self.s.post(
            f"{BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        data = r.json()
        if data.get("code") != 0:
            raise FeishuError(f"tenant token failed: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + int(data.get("expire", 7200))
        return self._token

    def _req(self, method, path, **kw):
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token()}"
        last = None
        for attempt in range(3):
            r = self.s.request(method, f"{BASE}{path}", headers=headers, timeout=60, **kw)
            try:
                data = r.json()
            except ValueError:
                raise FeishuError(f"{method} {path}: non-json response {r.status_code} {r.text[:200]}")
            code = data.get("code")
            if code == 0:
                return data.get("data", {})
            if r.status_code == 401 or code in (99991663, 99991661):
                self._token = None  # stale token, refresh and retry
                headers["Authorization"] = f"Bearer {self.token()}"
                last = data
                continue
            raise FeishuError(
                f"{method} {path} failed: code={code} msg={data.get('msg')} "
                f"body={json.dumps(data, ensure_ascii=False)[:400]}"
            )
        raise FeishuError(f"{method} {path} failed after retries: {last}")

    # --------------------------------------------------------------- bitable
    def list_fields(self):
        items = []
        token = None
        while True:
            params = {"page_size": 200}
            if token:
                params["page_token"] = token
            data = self._req(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
                params=params,
            )
            items.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            token = data.get("page_token")
        return items

    def search_records(self, *, view_id=None, page_size=500, page_token=None,
                       field_names=None, filter=None, sort=None):
        body = {}
        if view_id:
            body["view_id"] = view_id
        if field_names:
            body["field_names"] = field_names
        if filter:
            body["filter"] = filter
        if sort:
            body["sort"] = sort
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        return self._req(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/search",
            params=params,
            json=body,
        )

    def iter_records(self, page_size=500, **kw):
        token = None
        while True:
            data = self.search_records(page_token=token, page_size=page_size, **kw)
            yield from data.get("items", [])
            if not data.get("has_more"):
                break
            token = data.get("page_token")

    def create_field(self, name, ftype, property=None):
        body = {"field_name": name, "type": ftype}
        if property is not None:
            body["property"] = property
        return self._req(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
            json=body,
        )

    def update_record(self, record_id, fields):
        return self._req(
            "PUT",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}",
            json={"fields": fields},
        )

    def get_record(self, record_id):
        return self._req(
            "GET",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}",
        )

    # ----------------------------------------------------------------- drive
    def upload_media(self, file_path: Path, parent_type="bitable_image"):
        """Upload an image/file to the base. Returns file_token."""
        file_path = Path(file_path)
        size = file_path.stat().st_size
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "image/png")}
            data = {
                "file_name": file_path.name,
                "parent_type": parent_type,
                "parent_node": self.app_token,
                "size": str(size),
            }
            headers = {"Authorization": f"Bearer {self.token()}"}
            r = self.s.post(
                f"{BASE}/drive/v1/medias/upload_all",
                headers=headers,
                data=data,
                files=files,
                timeout=120,
            )
        resp = r.json()
        if resp.get("code") != 0:
            raise FeishuError(f"upload_media failed: {resp}")
        return resp["data"]["file_token"]


# ---------------------------------------------------------------- normalize
def plain(value):
    """Normalize a bitable field value structure to a plain python value."""
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        first = value[0]
        if isinstance(first, dict) and "text" in first:
            return first["text"]
        if isinstance(first, dict) and "name" in first:
            return first["name"]
        return plain(first)
    if isinstance(value, dict):
        if "value" in value:
            return plain(value["value"])
        if "text" in value:
            return value["text"]
        return None
    return value


def record_plain(fields: dict) -> dict:
    return {k: plain(v) for k, v in fields.items()}
