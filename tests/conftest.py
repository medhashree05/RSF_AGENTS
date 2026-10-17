import pytest

def is_docker_available() -> bool:
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False

docker_available = is_docker_available()

@pytest.fixture(autouse=True)
def auto_skip_docker_tests(request):
    """Skip tests marked with 'docker' if Docker daemon is not running."""
    if request.node.get_closest_marker("docker") and not docker_available:
        pytest.skip("Docker daemon is not running or accessible on this host.")
