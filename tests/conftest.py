import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts  # noqa: E402


@pytest.fixture()
def tmp_app(tmp_path):
    os.environ["PHYTOBRIDGE_USERS_DB"] = str(tmp_path / "users.db")
    accounts.USERS_DB_PATH = str(tmp_path / "users.db")
    # rebuild the store against the temp path
    accounts._RATE.clear()
    accounts_store = accounts.UserStore(str(tmp_path / "users.db"))
    import app as appmod
    appmod.store = accounts_store
    # point the app at the committed evidence db
    appmod.DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "phytobridge.db")
    appmod.app.config["TESTING"] = True
    yield appmod.app
