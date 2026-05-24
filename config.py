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

    # When set, the UI requires entering this password before /api/run can be called.
    # Leave empty to disable password protection entirely.
    demo_password: str = ""
    demo_token_ttl_hours: int = 24

    # Slack approval gate for sensitive cases (refund / outage / high-risk).
    # If all three are set, the orchestrator pauses on sensitive cases and posts
    # an Approve/Reject message to the configured channel before deciding.
    # Leave any of them empty to disable the gate (falls back to direct escalation).
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_approval_channel_id: str = ""
    slack_approval_timeout_seconds: int = 600  # 10 min


settings = Settings()
