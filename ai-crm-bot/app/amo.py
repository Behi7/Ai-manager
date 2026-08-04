from __future__ import annotations

from typing import Any

import httpx

from .config import FIELDS, FIELD_BY_KEY, settings


class AmoCRMError(Exception):
    pass


class AmoCRMClient:
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.amo_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not settings.amo_base_url or not settings.amo_token:
            raise AmoCRMError("amoCRM is not configured")

        url = settings.amo_base_url.rstrip("/") + path

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                **kwargs,
            )

        if response.status_code >= 400:
            raise AmoCRMError(
                f"amoCRM error {response.status_code}: {response.text[:500]}"
            )

        if not response.text:
            return {}

        return response.json()

    def _contact_custom_fields(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []

        phone = draft.get("phone")
        if phone:
            values.append(
                {
                    "field_code": "PHONE",
                    "values": [{"value": str(phone)}],
                }
            )

        return values

    def _lead_custom_fields(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []

        for field in FIELDS:
            if field["amo_target"] != "lead":
                continue

            field_id = field.get("amo_field_id")
            if not field_id:
                continue

            value = draft.get(field["key"])
            if value is None or str(value).strip() == "":
                continue

            values.append(
                {
                    "field_id": field_id,
                    "values": [{"value": str(value)}],
                }
            )

        return values

    async def create_contact(self, draft: dict[str, Any]) -> int:
        payload: dict[str, Any] = {
            "name": draft.get("name") or "Клиент Telegram",
        }

        custom_fields = self._contact_custom_fields(draft)
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        data = await self._request(
            "POST",
            "/api/v4/contacts",
            json=payload,
        )

        return data["_embedded"]["contacts"][0]["id"]

    async def update_contact(
        self,
        contact_id: int,
        draft: dict[str, Any],
    ) -> int:
        payload: dict[str, Any] = {}

        if draft.get("name"):
            payload["name"] = draft["name"]

        custom_fields = self._contact_custom_fields(draft)
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        if payload:
            await self._request(
                "PATCH",
                f"/api/v4/contacts/{contact_id}",
                json=payload,
            )

        return contact_id

    async def create_lead(
        self,
        draft: dict[str, Any],
        contact_id: int,
        status_id: int | None = None,
    ) -> int:
        payload: dict[str, Any] = {
            "name": f"Заявка: {draft.get('name') or 'Клиент'}",
            "_embedded": {
                "contacts": [
                    {"id": contact_id},
                ]
            },
        }

        if status_id:
            payload["status_id"] = status_id

        custom_fields = self._lead_custom_fields(draft)
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        data = await self._request(
            "POST",
            "/api/v4/leads",
            json=payload,
        )

        return data["_embedded"]["leads"][0]["id"]

    async def get_contact_draft(self, contact_id: int) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/api/v4/contacts/{contact_id}?with=custom_fields_values",
        )

        draft: dict[str, Any] = {}

        if data.get("name"):
            draft["name"] = data["name"]

        field_id_to_key = {
            field["amo_field_id"]: field["key"]
            for field in FIELDS
            if field.get("amo_field_id")
        }

        for custom_field in data.get("custom_fields_values", []) or []:
            field_id = custom_field.get("field_id")
            field_code = custom_field.get("field_code")
            values = custom_field.get("values") or []

            if not values:
                continue

            value = values[0].get("value")

            if field_code == "PHONE" and "phone" in FIELD_BY_KEY:
                draft["phone"] = value

            if field_id in field_id_to_key:
                draft[field_id_to_key[field_id]] = value

        return draft

    async def submit_final(
        self,
        draft: dict[str, Any],
        existing_contact_id: int | None = None,
    ) -> tuple[int, int]:
        if existing_contact_id:
            contact_id = await self.update_contact(existing_contact_id, draft)
        else:
            contact_id = await self.create_contact(draft)

        lead_id = await self.create_lead(draft, contact_id)

        return contact_id, lead_id

    async def submit_handoff(
        self,
        draft: dict[str, Any],
        existing_contact_id: int | None = None,
        reason: str = "",
    ) -> tuple[int, int]:
        # MVP: без специального статуса "требует уточнения менеджером".
        # В продакшене нужно заранее создать статус/этап и передавать status_id.
        if existing_contact_id:
            contact_id = existing_contact_id
        else:
            contact_id = await self.create_contact(draft)

        lead_id = await self.create_lead(draft, contact_id)

        return contact_id, lead_id