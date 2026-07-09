# Docker Hub jupyter/* images are frozen since 2023-10-20 (Ubuntu 22.04, glibc 2.35).
# The Antigravity SDK's bundled localharness binary needs GLIBC_ABI_DT_RELR (glibc >= 2.36).
# Use the maintained quay.io python-3.12 tag: Ubuntu 24.04 (glibc 2.39, satisfies the
# binary) and Python 3.12 to match the backend image and let numpy==2.5.1 install
# (numpy 2.5.x requires Python >= 3.12). Avoid :latest (Python 3.13) — newer, with
# thinner compiled-wheel coverage and no benefit here.
FROM quay.io/jupyter/scipy-notebook:python-3.12

WORKDIR /notebooks

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

EXPOSE 8888

# A fixed token is set so VS Code's Jupyter extension can validate & connect to
# this server ("Existing Jupyter Server..." -> http://localhost:8020/?token=vb).
# An empty token works in the browser but VS Code's URL validator silently rejects it.
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--IdentityProvider.token=vb", "--ServerApp.disable_check_xsrf=True", "--ServerApp.allow_origin=*", "--ServerApp.allow_remote_access=True"]
