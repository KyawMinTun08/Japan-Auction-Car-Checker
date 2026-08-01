from setuptools import setup


setup(
    name="jacc-runtime-patches",
    version="0.1.1",
    description="Runtime patches for the JACC Telegram bot rollout",
    py_modules=["sitecustomize", "usercustomize"],
)
