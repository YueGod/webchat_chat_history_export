#!/usr/bin/env python3
"""WeChat Chat Viewer — pywebview entry point."""

import logging
import os
import sys

import webview

from app.api import Api


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    web_dir = os.path.join(os.path.dirname(__file__), "app", "web")

    api = Api()
    window = webview.create_window(
        title="WeChat Chat Viewer",
        url=os.path.join(web_dir, "index.html"),
        js_api=api,
        width=1140,
        height=760,
        min_size=(900, 600),
        background_color="#0f0f0f",
        text_select=True,
    )
    api.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
