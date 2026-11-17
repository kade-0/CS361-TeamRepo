import requests

BASE_URL = "https://localhost:8320"
TEST_EMAIL = "test@test.com"
TEST_PASSWORD = "tester"
TEST_DISPLAY_NAME = "tester"

def test_account_registration(email: str, password: str, display_name: str):
	response = requests.post(
		f"{BASE_URL}/register",
		json={
			"email": email,
			"password": password,
			"displayName": display_name,
		},
		verify=False
	)
	return response

def test_account_login(email: str, password: str):
	response = requests.post(
		f"{BASE_URL}/login",
		json={
			"email": email,
			"password": password,
		},
		verify=False
	)
	return response

def test_account_logout(token: str):
	response = requests.post(
		f"{BASE_URL}/logout",
		headers={
			"Authorization": f"Bearer {token}",
		},
		verify=False
	)
	return response