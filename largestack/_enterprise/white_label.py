"""White-labeling — custom branding for enterprise customers."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class WhiteLabelConfig:
    """Custom branding configuration."""

    company_name: str = "Largestack AI"
    logo_url: str = ""
    primary_color: str = "#7c6cf0"
    dashboard_title: str = "Largestack AI Dashboard"
    error_prefix: str = "LARGESTACK"
    docs_url: str = "https://docs.largestack.ai"
    support_email: str = "support@largestack.ai"
    custom_css: str = ""
    hide_powered_by: bool = False
    custom_domain: str = ""

    def apply_to_error(self, error_msg: str) -> str:
        if self.error_prefix != "LARGESTACK":
            return error_msg.replace("LARGESTACK", self.error_prefix)
        return error_msg

    def get_dashboard_css(self) -> str:
        css = f":root {{ --primary: {self.primary_color}; }}"
        if self.custom_css:
            css += f"\n{self.custom_css}"
        return css
