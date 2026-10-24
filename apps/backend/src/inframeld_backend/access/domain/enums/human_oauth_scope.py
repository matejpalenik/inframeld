from enum import StrEnum


class HumanOAuthScope(StrEnum):
    OPENID = "openid"
    OFFLINE_ACCESS = "offline_access"
    API = "inframeld:api"
