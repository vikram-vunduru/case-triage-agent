from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    salesforce_mode: str = "mock"
    confluence_mode: str = "mock"

    sf_username: str = ""
    sf_password: str = ""
    sf_security_token: str = ""
    sf_domain: str = "login"
    sf_consumer_key: str = ""
    sf_consumer_secret: str = ""
    sf_login_url: str = ""

    confluence_url: str = ""
    confluence_username: str = ""
    confluence_api_token: str = ""
    confluence_space_key: str = ""

    confidence_threshold: float = 0.6
    require_human_approval: bool = False

    route_prefix: str = ""


settings = Settings()
