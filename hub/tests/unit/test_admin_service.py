import pytest

from app.models.user import User
from app.services.admin_service import AdminService
from tests.unit.fakes import FakeAuditRepository, FakeHubStateRepository


def make_admin() -> User:
    user = User(email="admin@amp.local", name="Admin", password_hash="x")
    user.id = 1
    user.role = "admin"
    return user


@pytest.fixture
def audit() -> FakeAuditRepository:
    return FakeAuditRepository()


@pytest.fixture
def service(audit) -> AdminService:
    return AdminService(state=FakeHubStateRepository(), audit=audit)


class TestKillSwitch:
    async def test_default_enabled(self, service):
        assert await service.get_kill_switch() is True

    async def test_disable_then_enable_and_audit(self, service, audit):
        admin = make_admin()

        assert await service.set_kill_switch(admin, enabled=False) is False
        assert await service.get_kill_switch() is False
        assert audit.has("kill_switch_toggled")

        assert await service.set_kill_switch(admin, enabled=True) is True
        assert await service.get_kill_switch() is True
