import sys, json
sys.path.insert(0, 'ai-crm-bot')
from app.amo import AmoCRMClient

draft = {
    'name': 'Тест Пользователь',
    'phone': '+998901234568',
    'address': 'ул. Примерная, 1',
    'sqm': 30.0,
    'budget': '100000 рублей',
}
client = AmoCRMClient()
contact_payload = {'name': draft.get('name')}
custom_fields = client._contact_custom_fields(draft)
if custom_fields:
    contact_payload['custom_fields_values'] = custom_fields
print('CONTACT PAYLOAD:')
print(json.dumps(contact_payload, ensure_ascii=False, indent=2))
lead_payload = {
    'name': f"Заявка: {draft['name']}",
    '_embedded': {'contacts': [{'id': 123}]},
}
lead_custom = client._lead_custom_fields(draft)
if lead_custom:
    lead_payload['custom_fields_values'] = lead_custom
print('\nLEAD PAYLOAD:')
print(json.dumps(lead_payload, ensure_ascii=False, indent=2))
