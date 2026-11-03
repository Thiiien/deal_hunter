from urllib.parse import quote

from .config import Config


class AffiliateLinker:
    """Builds affiliate-tagged URLs from templates configured in .env.

    Template variables: {raw} = original URL, {url} = URL-encoded original URL.
    Every link leaving the system (bot, dashboard) MUST go through build().
    """

    def __init__(self, config: Config):
        self._templates = {
            "shopee": config.aff_shopee,
            "lazada": config.aff_lazada,
            "tiktok": config.aff_tiktok,
        }

    def build(self, platform: str, raw_url: str) -> str:
        tpl = self._templates.get(platform, "{raw}")
        return tpl.replace("{raw}", raw_url).replace("{url}", quote(raw_url, safe=""))
