from __future__ import annotations

from typing import Any
import logging

import httpx

from . import fields
from .config import settings

logger = logging.getLogger(__name__)


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

        logger.debug(
            "AmoCRM %s %s request payload=%s status=%s response=%s",
            method,
            url,
            kwargs.get("json"),
            response.status_code,
            response.text[:1000],
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

        for field in fields.FIELDS:
            if field["amo_target"] != "contact":
                continue

            key = field["key"]
            if key == "name":
                continue

            value = draft.get(key)
            if value is None or str(value).strip() == "":
                continue

            field_id = field.get("amo_field_id")
            if field_id:
                values.append(
                    {
                        "field_id": field_id,
                        "values": [{"value": str(value)}],
                    }
                )
                continue

            if key == "phone":
                values.append(
                    {
                        "field_code": "PHONE",
                        "values": [{"value": str(value)}],
                    }
                )

        return values

    def _contact_payload(self, draft: dict[str, Any], name_as_array: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {}

        name = draft.get("name")
        if name is not None and str(name).strip() != "":
            if name_as_array:
                payload["name"] = [str(name)]
            else:
                payload["name"] = str(name)

        custom_fields = self._contact_custom_fields(draft)
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        return payload

    async def create_contact(self, draft: dict[str, Any]) -> int:
        payload = self._contact_payload(draft)

        try:
            data = await self._request(
                "POST",
                "/api/v4/contacts",
                json=payload,
            )
        except AmoCRMError as exc:
            message = str(exc)
            if "InvalidType" in message and "path\":\"name\"" in message:
                alternate = self._contact_payload(draft, name_as_array=True)
                if alternate != payload:
                    data = await self._request(
                        "POST",
                        "/api/v4/contacts",
                        json=alternate,
                    )
                else:
                    raise
            else:
                raise

        return data["_embedded"]["contacts"][0]["id"]

    async def update_contact(
        self,
        contact_id: int,
        draft: dict[str, Any],
    ) -> int:
        payload = self._contact_payload(draft)

        if payload:
            try:
                await self._request(
                    "PATCH",
                    f"/api/v4/contacts/{contact_id}",
                    json=payload,
                )
            except AmoCRMError as exc:
                message = str(exc)
                if "InvalidType" in message and "path\":\"name\"" in message:
                    alternate = self._contact_payload(draft, name_as_array=True)
                    if alternate != payload:
                        await self._request(
                            "PATCH",
                            f"/api/v4/contacts/{contact_id}",
                            json=alternate,
                        )
                    else:
                        raise
                else:
                    raise

        return contact_id

    def _lead_custom_fields(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []

        for field in fields.FIELDS:
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

    def _lead_payload(
        self,
        draft: dict[str, Any],
        contact_id: int,
        status_id: int | None = None,
        name_as_array: bool = True,
        is_update: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "_embedded": {
                "contacts": [
                    {"id": contact_id},
                ]
            },
        }

        name = draft.get("name")
        if name is not None and str(name).strip() != "":
            if name_as_array:
                payload["name"] = [f"Заявка: {name}"]
            else:
                payload["name"] = f"Заявка: {name}"
        elif not is_update:  # Только для создания, не для обновления
            payload["name"] = ["Заявка: Клиент"]

        if status_id:
            payload["status_id"] = status_id

        custom_fields = self._lead_custom_fields(draft)
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        return payload

    async def create_lead(
        self,
        draft: dict[str, Any],
        contact_id: int,
        status_id: int | None = None,
    ) -> int:
        payload = self._lead_payload(draft, contact_id, status_id=status_id)

        try:
            data = await self._request(
                "POST",
                "/api/v4/leads",
                json=payload,
            )
        except AmoCRMError as exc:
            message = str(exc)
            if "InvalidType" in message and "path\":\"name\"" in message:
                alternate = self._lead_payload(
                    draft,
                    contact_id,
                    status_id=status_id,
                    name_as_array=True,
                )
                if alternate != payload:
                    data = await self._request(
                        "POST",
                        "/api/v4/leads",
                        json=alternate,
                    )
                else:
                    raise
            else:
                raise

        return data["_embedded"]["leads"][0]["id"]

    async def update_lead(
        self,
        lead_id: int,
        draft: dict[str, Any],
        contact_id: int,
        status_id: int | None = None,
    ) -> int:
        # Для обновления используем is_update=True и name_as_array=False
        payload = self._lead_payload(draft, contact_id, status_id=status_id, name_as_array=False, is_update=True)

        logger.info(f"update_lead payload: {payload}")

        if payload:
            try:
                await self._request(
                    "PATCH",
                    f"/api/v4/leads/{lead_id}",
                    json=payload,
                )
            except AmoCRMError as exc:
                message = str(exc)
                logger.info(f"PATCH error: {message}")
                if "InvalidType" in message and "path\":\"name\"" in message:
                    alternate = self._lead_payload(
                        draft,
                        contact_id,
                        status_id=status_id,
                        name_as_array=True,
                        is_update=True,
                    )
                    logger.info(f"Alternate payload: {alternate}")
                    if alternate != payload:
                        await self._request(
                            "PATCH",
                            f"/api/v4/leads/{lead_id}",
                            json=alternate,
                        )
                    else:
                        raise
                else:
                    raise

        return lead_id

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
            for field in fields.FIELDS
            if field.get("amo_field_id")
        }

        for custom_field in data.get("custom_fields_values", []) or []:
            field_id = custom_field.get("field_id")
            field_code = custom_field.get("field_code")
            values = custom_field.get("values") or []

            if not values:
                continue

            value = values[0].get("value")

            if field_code == "PHONE" and "phone" in fields.FIELD_BY_KEY:
                draft["phone"] = value

            if field_id in field_id_to_key:
                draft[field_id_to_key[field_id]] = value

        return draft

    async def submit_final(
        self,
        draft: dict[str, Any],
        existing_contact_id: int | None = None,
        existing_lead_id: int | None = None,
    ) -> tuple[int, int]:
        if existing_contact_id:
            contact_id = await self.update_contact(existing_contact_id, draft)
        else:
            contact_id = await self.create_contact(draft)

        if existing_lead_id:
            lead_id = await self.update_lead(existing_lead_id, draft, contact_id)
        else:
            lead_id = await self.create_lead(draft, contact_id)

        return contact_id, lead_id

    async def submit_handoff(
        self,
        draft: dict[str, Any],
        existing_contact_id: int | None = None,
        existing_lead_id: int | None = None,
        reason: str = "",
    ) -> tuple[int, int]:
        # MVP: без специального статуса "требует уточнения менеджером".
        # В продакшене нужно заранее создать статус/этап и передавать status_id.
        if existing_contact_id:
            contact_id = existing_contact_id
        else:
            contact_id = await self.create_contact(draft)

        if existing_lead_id:
            lead_id = await self.update_lead(existing_lead_id, draft, contact_id)
        else:
            lead_id = await self.create_lead(draft, contact_id)

        return contact_id, lead_id

    async def create_note(self, element_id: int, note_type: str, text: str, element_type: str = "lead"):
        """
        Создает заметку в amoCRM.

        :param element_id: ID сделки (lead) или контакта (contact).
        :param note_type: Тип заметки, например 'common'.
                           Возможные значения зависят от amoCRM, 'common' - это общая заметка.
        :param text: Текст заметки.
        :param element_type: 'lead' или 'contact'. По умолчанию 'lead'.
        """
        if element_type not in ["lead", "contact"]:
            raise ValueError("element_type must be 'lead' or 'contact'")

        entity_type_plural = f"{element_type}s"

        payload = [
            {
                "entity_id": element_id,
                "note_type": note_type,
                "params": {
                    "text": text
                }
            }
        ]

        try:
            data = await self._request(
                "POST",
                f"/api/v4/{entity_type_plural}/{element_id}/notes",
                json=payload,
            )
            logger.info(f"Note added to {element_type} {element_id} in amoCRM")
        except AmoCRMError as e:
            logger.error(f"Failed to add note to {element_type} {element_id} in amoCRM: {e}")
            raise

    async def get_account_custom_fields(self) -> dict[str, Any]:
        """
        Получает кастомные поля для контактов и сделок через отдельные эндпоинты.
        """
        try:
            # Получаем кастомные поля контактов
            contact_data = await self._request(
                "GET",
                "/api/v4/contacts/custom_fields",
            )
            contact_fields = contact_data.get("_embedded", {}).get("custom_fields", [])
            
            # Получаем кастомные поля сделок
            lead_data = await self._request(
                "GET",
                "/api/v4/leads/custom_fields",
            )
            lead_fields = lead_data.get("_embedded", {}).get("custom_fields", [])
            
            custom_fields = {
                "contacts": contact_fields,
                "leads": lead_fields
            }
            
            logger.info(f"Retrieved custom fields: contacts={len(contact_fields)}, leads={len(lead_fields)}")
            
            # Логируем первые несколько полей для отладки
            if contact_fields:
                logger.info(f"Sample contact fields: {contact_fields[:3]}")
            if lead_fields:
                logger.info(f"Sample lead fields: {lead_fields[:3]}")
            
            return custom_fields
        except Exception as e:
            logger.error(f"Error fetching custom fields: {e}")
            raise