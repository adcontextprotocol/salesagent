import requests

BASE_URL = "http://localhost:8004"

# Login
session = requests.Session()
login_resp = session.post(f"{BASE_URL}/test/auth", data={
    'email': 'test_super_admin@example.com',
    'password': 'test123'
})
print(f"Login status: {login_resp.status_code}")

# Try to update tenant name
update_resp = session.post(f"{BASE_URL}/tenant/default/settings/general", data={
    'name': 'Updated Publisher Name',
    'max_daily_budget': '10000',
    'enable_aee_signals': 'on',
    'human_review_required': 'on'
}, allow_redirects=False)

print(f"Update status: {update_resp.status_code}")
if update_resp.status_code == 302:
    print("✓ Tenant name update succeeded - redirected")
else:
    print(f"✗ Update failed: {update_resp.text[:200]}")
