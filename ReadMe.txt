HomeFinder Portal
A property management web application built with Flask and SQLite, featuring two-factor authentication (TOTP), AES-256-GCM PII encryption, and role-based access control.
Requirements

Python 3.10+ — https://www.python.org/downloads/


 Install Dependencies
Open a terminal and run: pip install flask pyjwt cryptography werkzeug pyotp pytest

 Running the Application
Navigate to the files/src folder and run:
bash
cd files/src
python app.py

You should see:
[DB] Schema initialised.
 * Running on http://127.0.0.1:5000
Then open your browser and go to:
 http://127.0.0.1:5000

The database and demo data are created automatically on first run.


 Demo Accounts
Role Username Password
Admin: admin  Admin1234!
Supervisor: supervisor Super5678!
User: user User9012!

 Two-Factor Authentication (2FA)
After entering username and password, the app asks for a 6-digit TOTP code.
To get the code for the demo accounts:

Open files/data/totp_code.txt (created automatically on first run)
Copy the TOTP secret for the account you want to log in with
Go to https://totp.app, paste the secret, and use the 6-digit code shown

Project Structure
HomeFinder_Portal/
└── files/
    ├── data/
    │   ├── homefinder.db          ← SQLite database (auto-created)
    │   └── totp_code.txt          ← TOTP secrets for demo accounts
    └── src/
        ├── app.py                 ← Entry point
        ├── models.py              ← Schema & encryption
        ├── dtos.py                ← Data Transfer Objects
        ├── factories.py           ← Factory Method pattern
        ├── strategies.py          ← Strategy pattern (tax calculation)
        ├── repositories/          ← Database access layer
        ├── services/              ← Business logic layer
        ├── routes/                ← Flask route handlers
        ├── templates/             ← HTML templates (Jinja2)
        └── static/                ← Property images
        └── tests/
            ├── conftest.py
            ├── test_auth_token_management.py
            ├── test_circuit_breaker.py
            ├── test_payment_pipeline.py
            ├── test_property_factory.py
            ├── test_rate_limiting.py
            └── test_tax_strategies.py

Key Pages
/ Home — featured properties
/register User registration
/login Login (credentials + TOTP)
/dashboard User dashboard
/properties Property listings & search
/admin/... Admin panel (admin only)
/supervisor/reports Monthly reports (supervisor only)

Navigate to the files folder (one level above src) and run:

cd files/src
python -m pytest tests/ -v

You should see output like:
========================= test session starts ========================
cachedir: .pytest_cache
rootdir: C:\Users\User\HomeFinder_Portal\files\src
plugins: anyio-4.13.0
collected 48 items  
tests/test_rate_limiting.py::TestRateLimiting::test_rate_limit_writes_audit_entry PASSED                  [ 75%]
tests/test_rate_limiting.py::TestRateLimiting::test_below_threshold_allows_login_to_proceed PASSED        [ 77%]
tests/test_rate_limiting.py::TestRateLimiting::test_login_attempt_repo_threshold_boundary PASSED          [ 79%]
tests/test_rate_limiting.py::TestRateLimiting::test_failed_credential_records_attempt PASSED              [ 81%]
tests/test_tax_strategies.py::TestTaxStrategies::test_residential_tax_is_2_percent PASSED                 [ 83%]
tests/test_tax_strategies.py::TestTaxStrategies::test_commercial_tax_is_5_percent PASSED                  [ 85%]
tests/test_tax_strategies.py::TestTaxStrategies::test_rental_tax_is_1_percent PASSED                      [ 87%]
tests/test_tax_strategies.py::TestTaxStrategies::test_price_with_tax_residential PASSED                   [ 89%]
tests/test_tax_strategies.py::TestTaxStrategies::test_price_with_tax_commercial PASSED                    [ 91%]
tests/test_tax_strategies.py::TestTaxStrategies::test_calculate_tax_via_composed_property_object PASSED   [ 93%]
tests/test_tax_strategies.py::TestTaxStrategies::test_strategy_registry_returns_correct_types PASSED      [ 95%]
tests/test_tax_strategies.py::TestTaxStrategies::test_unknown_category_raises_value_error PASSED          [ 97%]
tests/test_tax_strategies.py::TestTaxStrategies::test_tax_rounding_to_two_decimal_places PASSED           [100%]
================================ 48 passed in 0.26s ===============================

Run a specific test file

python -m pytest tests/test_tax_strategies.py -v
python -m pytest tests/test_property_factory.py -v
python -m pytest tests/test_payment_pipeline.py -v
python -m pytest tests/test_auth_token_management.py -v
python -m pytest tests/test_rate_limiting.py -v
python -m pytest tests/test_circuit_breaker.py -v

Test coverage summary
Test File 
test_tax_strategies.py
Tax calculation for each property type (2%, 5%, 1%)
test_property_factory.py Factory Method — correct subclass and strategy injection
test_payment_pipeline.py ACID payment flow, gateway mock, DB writes
test_auth_token_management.py JWT lifecycle — expiry, phase, leeway, 2FA success
test_rate_limiting.py Login rate limiting — threshold, audit log, blocking
test_circuit_breaker.py Circuit breaker states: CLOSED → OPEN → HALF_OPEN