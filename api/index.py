"""
Flask app — single entrypoint for all routes on Vercel.
Static files (HTML/CSS/JS) are embedded as base64 so Vercel bundles them.
"""
from __future__ import annotations
import base64 as _b64
import hashlib
import hmac
import json
import os
import sys
import time

# Make bot/ importable (sits one level above this file, same project root)
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from flask import Flask, Response, jsonify, make_response, request

from bot.supabase_db import SupabaseDB, SupabaseError

app = Flask(__name__)

# ─── Embedded static files ────────────────────────────────────────────

_STATIC_INDEX_HTML = "PCFET0NUWVBFIGh0bWw+CjxodG1sIGRpcj0icnRsIiBsYW5nPSJhciI+CjxoZWFkPgo8bWV0YSBjaGFyc2V0PSJ1dGYtOCIgLz4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIiIC8+CjxtZXRhIG5hbWU9InRoZW1lLWNvbG9yIiBjb250ZW50PSIjMjU2M2ViIiAvPgo8dGl0bGU+RWxteSBDViBCb3Qg4oCUINmF2YbYtdipINil2LHYs9in2YQg2KfZhNiz2YrYsSDYp9mE2LDYp9iq2YrYqTwvdGl0bGU+CjxsaW5rIHJlbD0ic3R5bGVzaGVldCIgaHJlZj0iL3N0eWxlLmNzcyIgLz4KPC9oZWFkPgo8Ym9keT4KICA8aGVhZGVyIGNsYXNzPSJ0b3BiYXIiPgogICAgPGRpdiBjbGFzcz0iYnJhbmQiPgogICAgICA8c3BhbiBjbGFzcz0ibG9nbyI+8J+TqDwvc3Bhbj4KICAgICAgPHNwYW4gY2xhc3M9InRpdGxlIj5FbG15IENWIEJvdDwvc3Bhbj4KICAgIDwvZGl2PgogICAgPGJ1dHRvbiBpZD0ibG9nb3V0QnRuIiBjbGFzcz0iZ2hvc3QgaGlkZGVuIj7Yrtix2YjYrDwvYnV0dG9uPgogIDwvaGVhZGVyPgoKICA8bWFpbiBpZD0iYXBwIj48L21haW4+CgogIDwhLS0gPT09PT0gVGVtcGxhdGVzID09PT09IC0tPgogIDx0ZW1wbGF0ZSBpZD0idHBsLWxvZ2luIj4KICAgIDxzZWN0aW9uIGNsYXNzPSJjYXJkIGNlbnRlciI+CiAgICAgIDxoMT7Yqtiz2KzZitmEINin2YTYr9iu2YjZhDwvaDE+CiAgICAgIDxwIGNsYXNzPSJtdXRlZCI+2KfZhNmF2YbYtdipINiu2KfYtdipLiDYo9iv2K7ZhCDZg9mE2YXYqSDYp9mE2YXYsdmI2LEg2YTZhNmF2KrYp9io2LnYqS48L3A+CiAgICAgIDxmb3JtIGlkPSJsb2dpbkZvcm0iIGNsYXNzPSJmb3JtIj4KICAgICAgICA8bGFiZWw+2YPZhNmF2Kkg2KfZhNmF2LHZiNixCiAgICAgICAgICA8aW5wdXQgdHlwZT0icGFzc3dvcmQiIG5hbWU9InBhc3N3b3JkIiByZXF1aXJlZCBhdXRvY29tcGxldGU9ImN1cnJlbnQtcGFzc3dvcmQiIC8+CiAgICAgICAgPC9sYWJlbD4KICAgICAgICA8YnV0dG9uIGNsYXNzPSJwcmltYXJ5IiB0eXBlPSJzdWJtaXQiPtiv2K7ZiNmEPC9idXR0b24+CiAgICAgICAgPGRpdiBjbGFzcz0iZXJyIiBpZD0ibG9naW5FcnIiPjwvZGl2PgogICAgICA8L2Zvcm0+CiAgICA8L3NlY3Rpb24+CiAgPC90ZW1wbGF0ZT4KCiAgPHRlbXBsYXRlIGlkPSJ0cGwtY2FtcGFpZ25zIj4KICAgIDxzZWN0aW9uIGNsYXNzPSJjYXJkIj4KICAgICAgPGRpdiBjbGFzcz0icm93IHNwcmVhZCI+CiAgICAgICAgPGgxPtin2YTYrdmF2YTYp9iqPC9oMT4KICAgICAgICA8ZGl2IGNsYXNzPSJyb3ciPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iZ2hvc3QiIGlkPSJpbXBvcnRCdG4iPvCfk6Ug2KfYs9iq2YrYsdin2K8g2LTYsdmD2KfYqiAoRXhjZWwpPC9idXR0b24+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJwcmltYXJ5IiBpZD0ibmV3Q2FtcGFpZ25CdG4iPisg2K3ZhdmE2Kkg2KzYr9mK2K/YqTwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgICAgPHAgY2xhc3M9Im11dGVkIHNtYWxsIj7YrdmF2YTYqSDZhNmD2YQg2LnZhdmK2YQg2YXZhiDYudmF2YTYp9im2YMuINmD2YQg2K3ZhdmE2Kkg2KrZj9ix2LPZhCDYpdmE2Ykg2YLYp9im2YXYqSDYp9mE2LTYsdmD2KfYqiDYp9mE2YPYp9mF2YTYqS48L3A+CiAgICAgIDxkaXYgaWQ9ImltcG9ydFJlc3VsdCIgY2xhc3M9Im11dGVkIHNtYWxsIiBzdHlsZT0ibWFyZ2luLXRvcDo2cHgiPjwvZGl2PgogICAgICA8ZGl2IGlkPSJjYW1wYWlnbkxpc3QiIGNsYXNzPSJjYW1wYWlnbi1saXN0Ij48L2Rpdj4KICAgIDwvc2VjdGlvbj4KICA8L3RlbXBsYXRlPgoKICA8dGVtcGxhdGUgaWQ9InRwbC1uZXctY2FtcGFpZ24iPgogICAgPHNlY3Rpb24gY2xhc3M9ImNhcmQiPgogICAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImJhY2tCdG4iPuKGkCDYsdis2YjYuTwvYnV0dG9uPgogICAgICA8aDE+2K3ZhdmE2Kkg2KzYr9mK2K/YqTwvaDE+CiAgICAgIDxwIGNsYXNzPSJtdXRlZCBzbWFsbCI+2KfYs9mFINin2YTYudmF2YrZhCAo2K/Yp9iu2YTZiiDZhNmE2KrZhdmK2YrYsikgKyDYqNmK2KfZhtin2Kog2KfZhNil2LHYs9in2YQuPC9wPgogICAgICA8Zm9ybSBpZD0ibmV3Q2FtcEZvcm0iIGNsYXNzPSJmb3JtIj4KICAgICAgICA8bGFiZWw+2KfYs9mFINin2YTYudmF2YrZhCAo2YTYqtmF2YrZitiyINin2YTYrdmF2YTYqSkKICAgICAgICAgIDxpbnB1dCBuYW1lPSJjdXN0b21lcl9sYWJlbCIgcmVxdWlyZWQgbWF4bGVuZ3RoPSI4MCIgcGxhY2Vob2xkZXI9ItmF2KvYp9mEOiDYo9it2YXYryAtINmF2LfZiNmR2LEg2LPZitmG2YrZiNixIiAvPgogICAgICAgIDwvbGFiZWw+CgogICAgICAgIDxsYWJlbD7ZhdmE2YEg2KfZhNmAIENWIChQREYg2YHZgti3KQogICAgICAgICAgPGlucHV0IHR5cGU9ImZpbGUiIG5hbWU9ImN2IiBhY2NlcHQ9ImFwcGxpY2F0aW9uL3BkZiIgcmVxdWlyZWQgLz4KICAgICAgICA8L2xhYmVsPgoKICAgICAgICA8bGFiZWw+2KfYs9mFINin2YTZhdix2LPZkNmEICjZiti42YfYsSDZhNmE2LTYsdmD2KkpCiAgICAgICAgICA8aW5wdXQgbmFtZT0ic2VuZGVyX25hbWUiIHJlcXVpcmVkIG1heGxlbmd0aD0iODAiIC8+CiAgICAgICAgPC9sYWJlbD4KCiAgICAgICAgPGRpdiBjbGFzcz0icm93Ij4KICAgICAgICAgIDxsYWJlbCBjbGFzcz0iZ3JvdyI+2LnZhtmI2KfZhiDYp9mE2KXZitmF2YrZhCAo2LnYsdio2YopCiAgICAgICAgICAgIDxpbnB1dCBuYW1lPSJzdWJqZWN0X2FyIiByZXF1aXJlZCBtYXhsZW5ndGg9IjEyMCIgdmFsdWU9Iti32YTYqCDYqtmI2LjZitmBIC0g2LPZitix2Kkg2LDYp9iq2YrYqSIgLz4KICAgICAgICAgIDwvbGFiZWw+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0icm93Ij4KICAgICAgICAgIDxsYWJlbCBjbGFzcz0iZ3JvdyI+2LnZhtmI2KfZhiDYp9mE2KXZitmF2YrZhCAoRW5nbGlzaCkKICAgICAgICAgICAgPGlucHV0IG5hbWU9InN1YmplY3RfZW4iIHJlcXVpcmVkIG1heGxlbmd0aD0iMTIwIiB2YWx1ZT0iSm9iIEFwcGxpY2F0aW9uIC0gQ1YiIC8+CiAgICAgICAgICA8L2xhYmVsPgogICAgICAgIDwvZGl2PgoKICAgICAgICA8bGFiZWw+2YbYtSDYp9mE2LHYs9in2YTYqSAo2LnYsdio2YopIOKAlCDZitiv2LnZhSA8Y29kZT57Y29tcGFueV9uYW1lfTwvY29kZT4g2Yg8Y29kZT57c2VuZGVyX25hbWV9PC9jb2RlPgogICAgICAgICAgPHRleHRhcmVhIG5hbWU9ImNvdmVyX2xldHRlcl9hciIgcm93cz0iNiIgcmVxdWlyZWQ+PC90ZXh0YXJlYT4KICAgICAgICA8L2xhYmVsPgogICAgICAgIDxsYWJlbD7Zhti1INin2YTYsdiz2KfZhNipIChFbmdsaXNoKQogICAgICAgICAgPHRleHRhcmVhIG5hbWU9ImNvdmVyX2xldHRlcl9lbiIgcm93cz0iNiIgcmVxdWlyZWQ+PC90ZXh0YXJlYT4KICAgICAgICA8L2xhYmVsPgoKICAgICAgICA8bGFiZWw+2KrYrti12LUg2KfZhNi52YXZitmEICjZitit2K/YryDYp9mE2LTYsdmD2KfYqiDYp9mE2YXYs9iq2YfYr9mB2KkpCiAgICAgICAgICA8c2VsZWN0IG5hbWU9InRhcmdldF9zZWN0b3IiIGlkPSJzZWN0b3JTZWxlY3QiIHJlcXVpcmVkPgogICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSIiPtis2KfYsdmKINin2YTYqtit2YXZitmELi4uPC9vcHRpb24+CiAgICAgICAgICA8L3NlbGVjdD4KICAgICAgICA8L2xhYmVsPgoKICAgICAgICA8bGFiZWw+2K3YrNmFINin2YTYqNin2YLYqSAo2LnYr9ivINin2YTYtNix2YPYp9iqKSDigJQg2KPZiCDYp9mD2KrYqCAwINmE2YPZhCDYp9mE2LTYsdmD2KfYqiDYp9mE2YXYqtin2K3YqQogICAgICAgICAgPGlucHV0IHR5cGU9Im51bWJlciIgbmFtZT0icGFja2FnZV9zaXplIiBtaW49IjEiIHZhbHVlPSI0MCIgcmVxdWlyZWQKICAgICAgICAgICAgcGxhY2Vob2xkZXI9ItmF2KvYp9mEOiA0MCIgc3R5bGU9IndpZHRoOjEwMCUiIC8+CiAgICAgICAgPC9sYWJlbD4KICAgICAgICA8cCBjbGFzcz0ibXV0ZWQgc21hbGwiPgogICAgICAgICAg2KfZhNio2YjYqiDZitiu2KrYp9ixINi02LHZg9in2Kog2LnYtNmI2KfYptmK2Kkg2YTZhSDYqtmP2LPYqtiu2K/ZhSDZgdmKINit2YXZhNin2Kog2LPYp9io2YLYqS4g2KfZg9iq2Kgg2KfZhNi52K/YryDYp9mE2LDZiiDYqtix2YrYr9mHLgogICAgICAgICAg2KXYsNinINin2YbYqtmH2Kog2KfZhNi02LHZg9in2Kog2KfZhNis2K/Zitiv2KnYjCDZitmP2LnYp9ivINin2LPYqtiu2K/Yp9mFINi02LHZg9in2Kog2LPYp9io2YLYqSDZhdi5INiq2YbYqNmK2Ycg2YjYp9i22K0uCiAgICAgICAgPC9wPgoKICAgICAgICA8bGFiZWwgY2xhc3M9InRvZ2dsZSI+CiAgICAgICAgICA8aW5wdXQgdHlwZT0iY2hlY2tib3giIG5hbWU9InVzZV9haSIgY2hlY2tlZCAvPgogICAgICAgICAgPHNwYW4+2KfYs9iq2K7Yr9mFINin2YTYsNmD2KfYoSDYp9mE2KfYtdi32YbYp9i52YogKEdlbWluaSkg2YTZg9iq2KfYqNipINix2LPYp9mE2Kkg2YXYrti12ZHYtdipINmE2YPZhCDYtNix2YPYqSAo2YXYuSDYsdis2YjYuSDYotmF2YYg2YTZhNmC2KfZhNioKTwvc3Bhbj4KICAgICAgICA8L2xhYmVsPgoKICAgICAgICA8YnV0dG9uIGNsYXNzPSJwcmltYXJ5IiB0eXBlPSJzdWJtaXQiIGlkPSJjcmVhdGVCdG4iPtil2YbYtNin2KEg2KfZhNit2YXZhNipPC9idXR0b24+CiAgICAgICAgPGRpdiBjbGFzcz0iZXJyIiBpZD0ibmV3RXJyIj48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJwcm9ncmVzcyBoaWRkZW4iIGlkPSJuZXdQcm9ncmVzcyI+2KzYp9ix2Yog2KfZhNix2YHYuS4uLjwvZGl2PgogICAgICA8L2Zvcm0+CiAgICA8L3NlY3Rpb24+CiAgPC90ZW1wbGF0ZT4KCiAgPHRlbXBsYXRlIGlkPSJ0cGwtY2FtcGFpZ24tZGV0YWlsIj4KICAgIDxzZWN0aW9uIGNsYXNzPSJjYXJkIj4KICAgICAgPGJ1dHRvbiBjbGFzcz0iZ2hvc3QiIGlkPSJiYWNrQnRuIj7ihpAg2LHYrNmI2Lk8L2J1dHRvbj4KICAgICAgPGgxIGlkPSJjZFRpdGxlIj7YrdmF2YTYqTwvaDE+CiAgICAgIDxkaXYgY2xhc3M9InN0YXR1cy1yb3ciPgogICAgICAgIDxzcGFuIGlkPSJjZFN0YXR1cyIgY2xhc3M9InBpbGwiPuKAlDwvc3Bhbj4KICAgICAgICA8ZGl2IGNsYXNzPSJhY3Rpb25zIj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9InByaW1hcnkiIGRhdGEtYWN0PSJhY3RpdmUiPuKWtiDYp9io2K/YozwvYnV0dG9uPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0id2FybiIgICAgZGF0YS1hY3Q9InBhdXNlZCI+4o+4INil2YrZgtin2YEg2YXYpNmC2Ko8L2J1dHRvbj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImRhbmdlciIgIGRhdGEtYWN0PSJzdG9wcGVkIj7ij7kg2KXZitmC2KfZgTwvYnV0dG9uPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iZ2hvc3QiICAgaWQ9InJlZnJlc2hTdGF0cyI+8J+UhCDYqtit2K/ZitirPC9idXR0b24+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgoKICAgICAgPGRpdiBjbGFzcz0iY291bnRzLWdyaWQiIGlkPSJjZENvdW50cyI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImJhciI+PGRpdiBpZD0iY2RCYXIiPjwvZGl2PjwvZGl2PgoKICAgICAgPGgyPtin2YTYtNix2YPYp9iqINin2YTYqtmKINmB2KrYrdiqINin2YTYpdmK2YXZitmEPC9oMj4KICAgICAgPGRpdiBpZD0iY2RPcGVucyIgY2xhc3M9Im9wZW5zLWxpc3QiPuKAlDwvZGl2PgogICAgPC9zZWN0aW9uPgogIDwvdGVtcGxhdGU+CgogIDxzY3JpcHQgc3JjPSIvYXBwLmpzIj48L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg=="
_STATIC_STYLE_CSS = "LyogRWxteSBDViBCb3Qg4oCUIG1vYmlsZS1maXJzdCBSVEwgKi8KCjpyb290IHsKICAtLWJnOiAjZjNmNWY5OwogIC0tY2FyZDogI2ZmZmZmZjsKICAtLXRleHQ6ICMxZjI5Mzc7CiAgLS1tdXRlZDogIzZiNzI4MDsKICAtLWxpbmU6ICNlNWU3ZWI7CiAgLS1hY2NlbnQ6ICMyNTYzZWI7CiAgLS1vazogIzE2YTM0YTsKICAtLXdhcm46ICNkOTc3MDY7CiAgLS1lcnI6ICNkYzI2MjY7CiAgLS1yYWRpdXM6IDE0cHg7CiAgLS1zaGFkb3c6IDAgMXB4IDJweCByZ2JhKDAsMCwwLC4wNCksIDAgNnB4IDE4cHggcmdiYSgwLDAsMCwuMDQpOwp9CgoqIHsgYm94LXNpemluZzogYm9yZGVyLWJveDsgfQpodG1sLCBib2R5IHsgbWFyZ2luOiAwOyBwYWRkaW5nOiAwOyBiYWNrZ3JvdW5kOiB2YXIoLS1iZyk7IGNvbG9yOiB2YXIoLS10ZXh0KTsKICBmb250LWZhbWlseTogLWFwcGxlLXN5c3RlbSwgQmxpbmtNYWNTeXN0ZW1Gb250LCAiU2Vnb2UgVUkiLCBUYWhvbWEsIEFyaWFsLCBzYW5zLXNlcmlmOwogIGZvbnQtc2l6ZTogMTZweDsgbGluZS1oZWlnaHQ6IDEuNTU7CiAgb3ZlcmZsb3cteDogaGlkZGVuOyBtYXgtd2lkdGg6IDEwMHZ3OyB9CmltZywgYnV0dG9uLCBpbnB1dCwgdGV4dGFyZWEgeyBtYXgtd2lkdGg6IDEwMCU7IH0KCi50b3BiYXIgewogIHBvc2l0aW9uOiBzdGlja3k7IHRvcDogMDsgei1pbmRleDogMTA7CiAgZGlzcGxheTogZmxleDsganVzdGlmeS1jb250ZW50OiBzcGFjZS1iZXR3ZWVuOyBhbGlnbi1pdGVtczogY2VudGVyOwogIHBhZGRpbmc6IDE0cHggMThweDsgYmFja2dyb3VuZDogdmFyKC0tY2FyZCk7CiAgYm9yZGVyLWJvdHRvbTogMXB4IHNvbGlkIHZhcigtLWxpbmUpOwp9Ci5icmFuZCB7IGRpc3BsYXk6IGZsZXg7IGFsaWduLWl0ZW1zOiBjZW50ZXI7IGdhcDogMTBweDsgZm9udC13ZWlnaHQ6IDcwMDsgfQouYnJhbmQgLmxvZ28geyBmb250LXNpemU6IDIycHg7IH0KLmJyYW5kIC50aXRsZSB7IGZvbnQtc2l6ZTogMThweDsgY29sb3I6IHZhcigtLWFjY2VudCk7IH0KCm1haW4geyBwYWRkaW5nOiAxNHB4OyBtYXgtd2lkdGg6IDcyMHB4OyBtYXJnaW46IDAgYXV0bzsgcGFkZGluZy1ib3R0b206IDgwcHg7IH0KCi5jYXJkIHsgYmFja2dyb3VuZDogdmFyKC0tY2FyZCk7IGJvcmRlci1yYWRpdXM6IHZhcigtLXJhZGl1cyk7IHBhZGRpbmc6IDE4cHg7CiAgYm94LXNoYWRvdzogdmFyKC0tc2hhZG93KTsgbWFyZ2luLWJvdHRvbTogMTRweDsgfQouY2FyZC5jZW50ZXIgeyB0ZXh0LWFsaWduOiBjZW50ZXI7IH0KLmNhcmQgaDEgeyBtYXJnaW46IDAgMCA2cHg7IGZvbnQtc2l6ZTogMjJweDsgfQouY2FyZCBoMiB7IG1hcmdpbjogMThweCAwIDhweDsgZm9udC1zaXplOiAxN3B4OyBjb2xvcjogdmFyKC0tbXV0ZWQpOyB9CgoubXV0ZWQgeyBjb2xvcjogdmFyKC0tbXV0ZWQpOyB9Ci5zbWFsbCB7IGZvbnQtc2l6ZTogMTNweDsgfQouaGlkZGVuIHsgZGlzcGxheTogbm9uZSAhaW1wb3J0YW50OyB9Ci5lcnIgeyBjb2xvcjogdmFyKC0tZXJyKTsgZm9udC1zaXplOiAxNHB4OyBtYXJnaW4tdG9wOiA4cHg7IG1pbi1oZWlnaHQ6IDE4cHg7IH0KLnByb2dyZXNzIHsgY29sb3I6IHZhcigtLWFjY2VudCk7IGZvbnQtd2VpZ2h0OiA2MDA7IG1hcmdpbi10b3A6IDhweDsgfQoKLnJvdyB7IGRpc3BsYXk6IGZsZXg7IGdhcDogMTBweDsgYWxpZ24taXRlbXM6IGNlbnRlcjsgZmxleC13cmFwOiB3cmFwOyB9Ci5yb3cuc3ByZWFkIHsganVzdGlmeS1jb250ZW50OiBzcGFjZS1iZXR3ZWVuOyB9Ci5yb3cgLmdyb3cgeyBmbGV4OiAxOyB9CgouZm9ybSB7IGRpc3BsYXk6IGdyaWQ7IGdhcDogMTRweDsgbWFyZ2luLXRvcDogMTZweDsgfQouZm9ybSBsYWJlbCB7IGRpc3BsYXk6IGdyaWQ7IGdhcDogNnB4OyBmb250LXdlaWdodDogNjAwOyBmb250LXNpemU6IDE0cHg7IH0KLmZvcm0gaW5wdXRbdHlwZT10ZXh0XSwgLmZvcm0gaW5wdXRbdHlwZT1wYXNzd29yZF0sIC5mb3JtIGlucHV0Om5vdChbdHlwZV0pLAouZm9ybSBpbnB1dFt0eXBlPWZpbGVdLCAuZm9ybSB0ZXh0YXJlYSB7CiAgd2lkdGg6IDEwMCU7IHBhZGRpbmc6IDExcHggMTJweDsgYm9yZGVyOiAxcHggc29saWQgdmFyKC0tbGluZSk7CiAgYm9yZGVyLXJhZGl1czogMTBweDsgZm9udDogaW5oZXJpdDsgYmFja2dyb3VuZDogI2ZhZmJmZDsKfQouZm9ybSB0ZXh0YXJlYSB7IGZvbnQtZmFtaWx5OiB1aS1tb25vc3BhY2UsICJDYXNjYWRpYSBDb2RlIiwgIkNvbnNvbGFzIiwgbW9ub3NwYWNlOyBmb250LXNpemU6IDEzLjVweDsgfQouZm9ybSBpbnB1dDpmb2N1cywgLmZvcm0gdGV4dGFyZWE6Zm9jdXMgewogIG91dGxpbmU6IG5vbmU7IGJvcmRlci1jb2xvcjogdmFyKC0tYWNjZW50KTsgYmFja2dyb3VuZDogI2ZmZjsKICBib3gtc2hhZG93OiAwIDAgMCAzcHggcmdiYSgzNywgOTksIDIzNSwgMC4xNSk7Cn0KLmZvcm0gY29kZSB7IGJhY2tncm91bmQ6ICNlZWYyZmY7IHBhZGRpbmc6IDFweCA2cHg7IGJvcmRlci1yYWRpdXM6IDZweDsgZm9udC1zaXplOiAxMi41cHg7IH0KLnRvZ2dsZSB7IGZsZXgtZGlyZWN0aW9uOiByb3c7IGFsaWduLWl0ZW1zOiBjZW50ZXI7IGdhcDogOHB4OyBmb250LXdlaWdodDogNTAwOyB9Ci50b2dnbGUgaW5wdXQgeyB3aWR0aDogYXV0bzsgfQoKYnV0dG9uIHsgY3Vyc29yOiBwb2ludGVyOyBmb250OiBpbmhlcml0OyBwYWRkaW5nOiAxMXB4IDE2cHg7CiAgYm9yZGVyLXJhZGl1czogMTBweDsgYm9yZGVyOiAxcHggc29saWQgdmFyKC0tbGluZSk7IGJhY2tncm91bmQ6ICNmZmY7IH0KYnV0dG9uLnByaW1hcnkgeyBiYWNrZ3JvdW5kOiB2YXIoLS1hY2NlbnQpOyBjb2xvcjogI2ZmZjsgYm9yZGVyLWNvbG9yOiB2YXIoLS1hY2NlbnQpOyB9CmJ1dHRvbi5wcmltYXJ5OmhvdmVyIHsgYmFja2dyb3VuZDogIzFkNGVkODsgfQpidXR0b24ud2FybiB7IGJhY2tncm91bmQ6IHZhcigtLXdhcm4pOyBjb2xvcjogI2ZmZjsgYm9yZGVyLWNvbG9yOiB2YXIoLS13YXJuKTsgfQpidXR0b24uZGFuZ2VyIHsgYmFja2dyb3VuZDogdmFyKC0tZXJyKTsgY29sb3I6ICNmZmY7IGJvcmRlci1jb2xvcjogdmFyKC0tZXJyKTsgfQpidXR0b24uZ2hvc3QgeyBiYWNrZ3JvdW5kOiB0cmFuc3BhcmVudDsgfQpidXR0b246ZGlzYWJsZWQgeyBvcGFjaXR5OiAuNTU7IGN1cnNvcjogbm90LWFsbG93ZWQ7IH0KCi5jYW1wYWlnbi1saXN0IHsgZGlzcGxheTogZ3JpZDsgZ2FwOiAxMHB4OyBtYXJnaW4tdG9wOiAxNHB4OyB9Ci5jYW1wLWNhcmQgeyBiYWNrZ3JvdW5kOiAjZmFmYmZkOyBib3JkZXI6IDFweCBzb2xpZCB2YXIoLS1saW5lKTsgYm9yZGVyLXJhZGl1czogMTJweDsKICBwYWRkaW5nOiAxNHB4OyBkaXNwbGF5OiBncmlkOyBnYXA6IDhweDsgY3Vyc29yOiBwb2ludGVyOyB0cmFuc2l0aW9uOiAuMTVzOyB9Ci5jYW1wLWNhcmQ6aG92ZXIgeyBib3JkZXItY29sb3I6IHZhcigtLWFjY2VudCk7IH0KLmNhbXAtY2FyZCAudG9wIHsgZGlzcGxheTogZmxleDsganVzdGlmeS1jb250ZW50OiBzcGFjZS1iZXR3ZWVuOyBhbGlnbi1pdGVtczogY2VudGVyOyB9Ci5jYW1wLWNhcmQgLm5hbWUgeyBmb250LXdlaWdodDogNzAwOyB9Ci5waWxsIHsgZGlzcGxheTogaW5saW5lLWJsb2NrOyBwYWRkaW5nOiAzcHggMTBweDsgYm9yZGVyLXJhZGl1czogOTk5cHg7IGZvbnQtc2l6ZTogMTJweDsKICBmb250LXdlaWdodDogNzAwOyB9Ci50YWcgeyBkaXNwbGF5OiBpbmxpbmUtYmxvY2s7IHBhZGRpbmc6IDJweCA4cHg7IGJvcmRlci1yYWRpdXM6IDZweDsKICBiYWNrZ3JvdW5kOiAjZWVmMmZmOyBjb2xvcjogdmFyKC0tYWNjZW50KTsgZm9udC1zaXplOiAxMXB4OyBmb250LXdlaWdodDogNjAwOwogIG1hcmdpbi1pbmxpbmUtc3RhcnQ6IDZweDsgfQoucGlsbC5kcmFmdCAgIHsgYmFja2dyb3VuZDogI2YzZjRmNjsgY29sb3I6ICMzNzQxNTE7IH0KLnBpbGwuYWN0aXZlICB7IGJhY2tncm91bmQ6ICNkY2ZjZTc7IGNvbG9yOiAjMTY2NTM0OyB9Ci5waWxsLnBhdXNlZCAgeyBiYWNrZ3JvdW5kOiAjZmVmM2M3OyBjb2xvcjogIzkyNDAwZTsgfQoucGlsbC5zdG9wcGVkIHsgYmFja2dyb3VuZDogI2ZlZTJlMjsgY29sb3I6ICM5OTFiMWI7IH0KLnBpbGwuZG9uZSAgICB7IGJhY2tncm91bmQ6ICNkYmVhZmU7IGNvbG9yOiAjMWU0MGFmOyB9CgouY291bnRzLWdyaWQgeyBkaXNwbGF5OiBncmlkOyBncmlkLXRlbXBsYXRlLWNvbHVtbnM6IHJlcGVhdCg0LCAxZnIpOyBnYXA6IDEwcHg7CiAgbWFyZ2luOiAxNnB4IDAgMTBweDsgfQouY291bnQtY2VsbCB7IGJhY2tncm91bmQ6ICNmYWZiZmQ7IGJvcmRlcjogMXB4IHNvbGlkIHZhcigtLWxpbmUpOyBib3JkZXItcmFkaXVzOiAxMHB4OwogIHRleHQtYWxpZ246IGNlbnRlcjsgcGFkZGluZzogMTBweCA2cHg7IH0KLmNvdW50LWNlbGwgLnYgeyBmb250LXNpemU6IDIwcHg7IGZvbnQtd2VpZ2h0OiA4MDA7IGNvbG9yOiB2YXIoLS1hY2NlbnQpOyB9Ci5jb3VudC1jZWxsIC5sIHsgZm9udC1zaXplOiAxMnB4OyBjb2xvcjogdmFyKC0tbXV0ZWQpOyB9CgouYmFyIHsgd2lkdGg6IDEwMCU7IGhlaWdodDogMTJweDsgYmFja2dyb3VuZDogI2VlZjJmZjsgYm9yZGVyLXJhZGl1czogOTk5cHg7IG92ZXJmbG93OiBoaWRkZW47IH0KLmJhciA+IGRpdiB7IGhlaWdodDogMTAwJTsgYmFja2dyb3VuZDogdmFyKC0tb2spOyB0cmFuc2l0aW9uOiB3aWR0aCAuM3M7IH0KCi5zdGF0dXMtcm93IHsgZGlzcGxheTogZmxleDsganVzdGlmeS1jb250ZW50OiBzcGFjZS1iZXR3ZWVuOyBhbGlnbi1pdGVtczogY2VudGVyOwogIG1hcmdpbjogMTRweCAwIDZweDsgZ2FwOiAxMHB4OyBmbGV4LXdyYXA6IHdyYXA7IH0KLnN0YXR1cy1yb3cgLmFjdGlvbnMgeyBkaXNwbGF5OiBmbGV4OyBnYXA6IDZweDsgZmxleC13cmFwOiB3cmFwOyB9Ci5zdGF0dXMtcm93IC5hY3Rpb25zIGJ1dHRvbiB7IHBhZGRpbmc6IDhweCAxMnB4OyBmb250LXNpemU6IDE0cHg7IH0KCi5vcGVucy1saXN0IHsgZGlzcGxheTogZ3JpZDsgZ2FwOiA2cHg7IG1heC1oZWlnaHQ6IDMyMHB4OyBvdmVyZmxvdy15OiBhdXRvOyB9Ci5vcGVuLWl0ZW0geyBwYWRkaW5nOiA4cHggMTBweDsgYmFja2dyb3VuZDogI2ZhZmJmZDsgYm9yZGVyOiAxcHggc29saWQgdmFyKC0tbGluZSk7CiAgYm9yZGVyLXJhZGl1czogOHB4OyBmb250LXNpemU6IDE0cHg7IGRpc3BsYXk6IGZsZXg7IGp1c3RpZnktY29udGVudDogc3BhY2UtYmV0d2VlbjsgfQoub3Blbi1pdGVtIC5tZXRhIHsgY29sb3I6IHZhcigtLW11dGVkKTsgZm9udC1zaXplOiAxMnB4OyB9CgpAbWVkaWEgKG1pbi13aWR0aDogNjAwcHgpIHsKICAuY291bnRzLWdyaWQgeyBncmlkLXRlbXBsYXRlLWNvbHVtbnM6IHJlcGVhdCg1LCAxZnIpOyB9Cn0K"
_STATIC_APP_JS = "LyogRWxteSBDViBCb3Qg4oCUIHNpbmdsZS1maWxlIGZyb250ZW5kICh2YW5pbGxhIEpTKS4KICogUmVuZGVycyB0ZW1wbGF0ZXMgaW50byAjYXBwLCBjYWxscyAvYXBpLyogZW5kcG9pbnRzLCBuZXZlciB0b3VjaGVzIFN1cGFiYXNlIGRpcmVjdGx5LgogKi8KInVzZSBzdHJpY3QiOwoKY29uc3QgJCA9IChzZWwsIHJvb3QgPSBkb2N1bWVudCkgPT4gcm9vdC5xdWVyeVNlbGVjdG9yKHNlbCk7CmNvbnN0ICQkID0gKHNlbCwgcm9vdCA9IGRvY3VtZW50KSA9PiBBcnJheS5mcm9tKHJvb3QucXVlcnlTZWxlY3RvckFsbChzZWwpKTsKY29uc3QgYXBwID0gJCgiI2FwcCIpOwoKY29uc3QgREVGQVVMVF9BUiA9IGDZgdix2YrZgiDYp9mE2KrZiNi42YrZgSDYp9mE2YPYsdmK2YUg2YHZiiB7Y29tcGFueV9uYW1lfdiMCgrZitiz2LnYr9mG2Yog2KfZhNiq2YLYr9mR2YUg2KjYt9mE2Kgg2YTZhNin2YbYttmF2KfZhSDYpdmE2Ykg2YHYsdmK2YIge2NvbXBhbnlfbmFtZX0uINij2LHZgdmCINmE2YPZhSDYs9mK2LHYqtmKINin2YTYsNin2KrZitipINmE2YTYp9i32YTYp9i5INi52YTZitmH2KcuCgrYo9i52KrZgtivINij2YYg2YXZh9in2LHYp9iq2Yog2YjYrtio2LHYqtmKINiz2KrZg9mI2YYg2KXYttin2YHYqSDZgtmK2ZHZhdipINmE2YHYsdmK2YLZg9mFLgoK2YXYuSDYrtin2YTYtSDYp9mE2KrZgtiv2YrYsdiMCntzZW5kZXJfbmFtZX1gOwoKY29uc3QgREVGQVVMVF9FTiA9IGBEZWFyIHtjb21wYW55X25hbWV9IEhpcmluZyBUZWFtLAoKSSBhbSB3cml0aW5nIHRvIGV4cHJlc3MgbXkgc3Ryb25nIGludGVyZXN0IGluIGpvaW5pbmcge2NvbXBhbnlfbmFtZX0uIFBsZWFzZSBmaW5kIG15IENWIGF0dGFjaGVkIGZvciB5b3VyIHJldmlldy4KCkkgYmVsaWV2ZSBteSBza2lsbHMgYW5kIGV4cGVyaWVuY2Ugd291bGQgYmUgYSB2YWx1YWJsZSBhZGRpdGlvbiB0byB5b3VyIHRlYW0uCgpCZXN0IHJlZ2FyZHMsCntzZW5kZXJfbmFtZX1gOwoKLy8gLS0tLS0tLS0tLSB0aW55IHJvdXRlciAtLS0tLS0tLS0tCmFzeW5jIGZ1bmN0aW9uIGluaXQoKSB7CiAgJCgiI2xvZ291dEJ0biIpLmFkZEV2ZW50TGlzdGVuZXIoImNsaWNrIiwgbG9nb3V0KTsKICBjb25zdCBhdXRoZWQgPSBhd2FpdCBjaGVja0F1dGgoKTsKICBpZiAoIWF1dGhlZCkgcmV0dXJuIHJlbmRlckxvZ2luKCk7CiAgcmVuZGVyQ2FtcGFpZ25zKCk7Cn0KCmFzeW5jIGZ1bmN0aW9uIGNoZWNrQXV0aCgpIHsKICB0cnkgewogICAgY29uc3QgciA9IGF3YWl0IGZldGNoKCIvYXBpL21lIik7CiAgICBpZiAoci5vaykgeyAkKCIjbG9nb3V0QnRuIikuY2xhc3NMaXN0LnJlbW92ZSgiaGlkZGVuIik7IHJldHVybiB0cnVlOyB9CiAgfSBjYXRjaCB7fQogICQoIiNsb2dvdXRCdG4iKS5jbGFzc0xpc3QuYWRkKCJoaWRkZW4iKTsKICByZXR1cm4gZmFsc2U7Cn0KCmFzeW5jIGZ1bmN0aW9uIGxvZ291dCgpIHsKICBhd2FpdCBmZXRjaCgiL2FwaS9sb2dpbiIsIHsgbWV0aG9kOiAiREVMRVRFIiB9KTsKICAkKCIjbG9nb3V0QnRuIikuY2xhc3NMaXN0LmFkZCgiaGlkZGVuIik7CiAgcmVuZGVyTG9naW4oKTsKfQoKZnVuY3Rpb24gdHBsSW50byhpZCkgewogIGFwcC5pbm5lckhUTUwgPSAiIjsKICBjb25zdCB0cGwgPSAkKCIjIiArIGlkKTsKICBhcHAuYXBwZW5kQ2hpbGQodHBsLmNvbnRlbnQuY2xvbmVOb2RlKHRydWUpKTsKfQoKLy8gLS0tLS0tLS0tLSBsb2dpbiAtLS0tLS0tLS0tCmZ1bmN0aW9uIHJlbmRlckxvZ2luKCkgewogIHRwbEludG8oInRwbC1sb2dpbiIpOwogICQoIiNsb2dpbkZvcm0iKS5hZGRFdmVudExpc3RlbmVyKCJzdWJtaXQiLCBhc3luYyAoZSkgPT4gewogICAgZS5wcmV2ZW50RGVmYXVsdCgpOwogICAgY29uc3QgZmQgPSBuZXcgRm9ybURhdGEoZS50YXJnZXQpOwogICAgY29uc3QgZXJyQm94ID0gJCgiI2xvZ2luRXJyIik7CiAgICBlcnJCb3gudGV4dENvbnRlbnQgPSAiIjsKICAgIHRyeSB7CiAgICAgIGNvbnN0IHIgPSBhd2FpdCBmZXRjaCgiL2FwaS9sb2dpbiIsIHsKICAgICAgICBtZXRob2Q6ICJQT1NUIiwKICAgICAgICBoZWFkZXJzOiB7ICJDb250ZW50LVR5cGUiOiAiYXBwbGljYXRpb24vanNvbiIgfSwKICAgICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7IHBhc3N3b3JkOiBmZC5nZXQoInBhc3N3b3JkIikgfSksCiAgICAgIH0pOwogICAgICBpZiAoIXIub2spIHsKICAgICAgICBjb25zdCBkID0gYXdhaXQgci5qc29uKCkuY2F0Y2goKCkgPT4gKHt9KSk7CiAgICAgICAgZXJyQm94LnRleHRDb250ZW50ID0gZC5lcnJvciB8fCAi2YPZhNmF2Kkg2KfZhNmF2LHZiNixINiu2KfYt9im2KkuIjsKICAgICAgICByZXR1cm47CiAgICAgIH0KICAgICAgJCgiI2xvZ291dEJ0biIpLmNsYXNzTGlzdC5yZW1vdmUoImhpZGRlbiIpOwogICAgICByZW5kZXJDYW1wYWlnbnMoKTsKICAgIH0gY2F0Y2ggKGVycikgewogICAgICBlcnJCb3gudGV4dENvbnRlbnQgPSAi2KrYudiw2ZHYsSDYp9mE2KfYqti12KfZhCDYqNin2YTYrtin2K/ZhS4iOwogICAgfQogIH0pOwp9CgovLyAtLS0tLS0tLS0tIGNhbXBhaWducyBsaXN0IC0tLS0tLS0tLS0KYXN5bmMgZnVuY3Rpb24gcmVuZGVyQ2FtcGFpZ25zKCkgewogIHRwbEludG8oInRwbC1jYW1wYWlnbnMiKTsKICAkKCIjbmV3Q2FtcGFpZ25CdG4iKS5hZGRFdmVudExpc3RlbmVyKCJjbGljayIsIHJlbmRlck5ld0NhbXBhaWduKTsKCiAgLy8gRXhjZWwgaW1wb3J0IGJ1dHRvbgogICQoIiNpbXBvcnRCdG4iKS5hZGRFdmVudExpc3RlbmVyKCJjbGljayIsICgpID0+IHsKICAgIGNvbnN0IGlucCA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImlucHV0Iik7CiAgICBpbnAudHlwZSA9ICJmaWxlIjsgaW5wLmFjY2VwdCA9ICIueGxzeCxhcHBsaWNhdGlvbi92bmQub3BlbnhtbGZvcm1hdHMtb2ZmaWNlZG9jdW1lbnQuc3ByZWFkc2hlZXRtbC5zaGVldCI7CiAgICBpbnAub25jaGFuZ2UgPSBhc3luYyAoKSA9PiB7CiAgICAgIGNvbnN0IGZpbGUgPSBpbnAuZmlsZXNbMF07IGlmICghZmlsZSkgcmV0dXJuOwogICAgICBjb25zdCByZXMgPSAkKCIjaW1wb3J0UmVzdWx0Iik7CiAgICAgIHJlcy50ZXh0Q29udGVudCA9ICLYrNin2LHZiiDYp9mE2KfYs9iq2YrYsdin2K8uLi4iOwogICAgICB0cnkgewogICAgICAgIGNvbnN0IHIgPSBhd2FpdCBmZXRjaCgiL2FwaS9pbXBvcnQiLCB7CiAgICAgICAgICBtZXRob2Q6ICJQT1NUIiwKICAgICAgICAgIGhlYWRlcnM6IHsgIkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi92bmQub3BlbnhtbGZvcm1hdHMtb2ZmaWNlZG9jdW1lbnQuc3ByZWFkc2hlZXRtbC5zaGVldCIsCiAgICAgICAgICAgICAgICAgICAgICJYLUZpbGVuYW1lIjogZmlsZS5uYW1lIH0sCiAgICAgICAgICBib2R5OiBmaWxlLAogICAgICAgIH0pOwogICAgICAgIGNvbnN0IGQgPSBhd2FpdCByLmpzb24oKTsKICAgICAgICBpZiAoIXIub2spIHsgcmVzLnRleHRDb250ZW50ID0gItiu2LfYozogIiArIChkLmVycm9yIHx8ICLZgdi02YQg2KfZhNin2LPYqtmK2LHYp9ivIik7IHJldHVybjsgfQogICAgICAgIHJlcy50ZXh0Q29udGVudCA9IGDinIUg2KrZhSDYp9iz2KrZitix2KfYryAke2QuaW1wb3J0ZWR9INi02LHZg9ipJHtkLnNraXBwZWQgPyBgIMK3INiq2K7Yt9mKICR7ZC5za2lwcGVkfWAgOiAiIn1gOwogICAgICB9IGNhdGNoIHsgcmVzLnRleHRDb250ZW50ID0gItiq2LnYsNmR2LEg2KfZhNin2KrYtdin2YQg2KjYp9mE2K7Yp9iv2YUuIjsgfQogICAgfTsKICAgIGlucC5jbGljaygpOwogIH0pOwoKICBjb25zdCBsaXN0ID0gJCgiI2NhbXBhaWduTGlzdCIpOwogIGxpc3QudGV4dENvbnRlbnQgPSAi2KzYp9ix2Yog2KfZhNiq2K3ZhdmK2YQuLi4iOwogIHRyeSB7CiAgICBjb25zdCByID0gYXdhaXQgZmV0Y2goIi9hcGkvY2FtcGFpZ25zIik7CiAgICBpZiAoci5zdGF0dXMgPT09IDQwMSkgcmV0dXJuIHJlbmRlckxvZ2luKCk7CiAgICBjb25zdCBkYXRhID0gYXdhaXQgci5qc29uKCk7CiAgICBpZiAoIWRhdGEuY2FtcGFpZ25zIHx8IGRhdGEuY2FtcGFpZ25zLmxlbmd0aCA9PT0gMCkgewogICAgICBsaXN0LmlubmVySFRNTCA9ICc8ZGl2IGNsYXNzPSJtdXRlZCBzbWFsbCI+2YTYpyDYqtmI2KzYryDYrdmF2YTYp9iqINio2LnYry4g2KfYqNiv2KMg2KjYpdmG2LTYp9ihINit2YXZhNipINis2K/Zitiv2KkuPC9kaXY+JzsKICAgICAgcmV0dXJuOwogICAgfQogICAgbGlzdC5pbm5lckhUTUwgPSAiIjsKICAgIGZvciAoY29uc3QgYyBvZiBkYXRhLmNhbXBhaWducykgbGlzdC5hcHBlbmRDaGlsZChjYW1wQ2FyZChjKSk7CiAgfSBjYXRjaCAoZSkgewogICAgbGlzdC50ZXh0Q29udGVudCA9ICLYqti52LDZkdixINiq2K3ZhdmK2YQg2KfZhNit2YXZhNin2KouIjsKICB9Cn0KCmZ1bmN0aW9uIGNhbXBDYXJkKGMpIHsKICBjb25zdCBkaXYgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCJkaXYiKTsKICBkaXYuY2xhc3NOYW1lID0gImNhbXAtY2FyZCI7CiAgY29uc3QgY291bnRzID0gYy5jb3VudHMgfHwge307CiAgY29uc3Qgc2VudCA9IGNvdW50cy5zZW50IHx8IDA7CiAgY29uc3QgdG90YWwgPSBjb3VudHMudG90YWwgfHwgMDsKICBjb25zdCBwa2cgPSBjLnBhY2thZ2Vfc2l6ZSA/IGDYqNin2YLYqSAke2MucGFja2FnZV9zaXplfWAgOiAi2KfZhNmC2KfYptmF2Kkg2KfZhNmD2KfZhdmE2KkiOwogIGNvbnN0IHNlY3RvciA9IGMudGFyZ2V0X3NlY3RvciA/IGA8c3BhbiBjbGFzcz0idGFnIj4ke2VzYyhzZWN0b3JMYWJlbChjLnRhcmdldF9zZWN0b3IpKX08L3NwYW4+YCA6ICIiOwogIGNvbnN0IG92ZXJsYXAgPSBjLm92ZXJsYXBfY291bnQKICAgID8gYCDCtyA8c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0td2FybikiPuKaoCAke2Mub3ZlcmxhcF9jb3VudH0g2YXZj9i52KfYrzwvc3Bhbj5gCiAgICA6ICIiOwogIGRpdi5pbm5lckhUTUwgPSBgCiAgICA8ZGl2IGNsYXNzPSJ0b3AiPgogICAgICA8c3BhbiBjbGFzcz0ibmFtZSI+JHtlc2MoYy5jdXN0b21lcl9sYWJlbCl9ICR7c2VjdG9yfTwvc3Bhbj4KICAgICAgPHNwYW4gY2xhc3M9InBpbGwgJHtjLnN0YXR1c30iPiR7c3RhdHVzQXIoYy5zdGF0dXMpfTwvc3Bhbj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ibXV0ZWQgc21hbGwiPgogICAgICAke3BrZ30gwrcg2KfZhNmF2LHYs9mQ2YQ6ICR7ZXNjKGMuc2VuZGVyX25hbWUpfSDCtyDYo9mP2LHYs9mEICR7c2VudH0g2YXZhiAke3RvdGFsfSR7Y291bnRzLmZhaWxlZCA/IGAgwrcg2YHYtNmEICR7Y291bnRzLmZhaWxlZH1gIDogIiJ9JHtvdmVybGFwfQogICAgPC9kaXY+CiAgYDsKICBkaXYuYWRkRXZlbnRMaXN0ZW5lcigiY2xpY2siLCAoKSA9PiByZW5kZXJDYW1wYWlnbkRldGFpbChjLmlkKSk7CiAgcmV0dXJuIGRpdjsKfQoKZnVuY3Rpb24gc3RhdHVzQXIocykgewogIHJldHVybiB7IGRyYWZ0OiAi2YXYs9mI2K/YqSIsIGFjdGl2ZTogItmK2LnZhdmEIiwgcGF1c2VkOiAi2YXYqtmI2YLZgSDZhdik2YLYqtmL2KciLAogICAgICAgICAgIHN0b3BwZWQ6ICLZhdiq2YjZgtmBIiwgZG9uZTogItin2YPYqtmF2YTYqiIgfVtzXSB8fCBzOwp9Cgpjb25zdCBTRUNUT1JfQVIgPSB7CiAgSGVhbHRoY2FyZTogIti12K3YqSIsIE1hcmtldGluZzogItiq2LPZiNmK2YIg2YjYpdi52YTYp9mGIiwgVGVjaG5vbG9neTogItiq2YLZhtmK2Kkg2YjYqNix2YXYrNipIiwKICBGaW5hbmNlOiAi2YXYp9mE2YrYqSDZiNio2YbZiNmDIiwgRW5naW5lZXJpbmc6ICLZh9mG2K/Ys9ipINmI2YXZgtin2YjZhNin2KoiLCBMZWdhbDogItmC2KfZhtmI2YYiLAogIFJldGFpbDogItiq2KzYstim2Kkg2YjYqtis2KfYsdipIiwgRWR1Y2F0aW9uOiAi2KrYudmE2YrZhSIsIEhSOiAi2YXZiNin2LHYryDYqNi02LHZitipIiwKICBIb3NwaXRhbGl0eTogIti22YrYp9mB2Kkg2YjZgdmG2KfYr9mCIiwgTG9naXN0aWNzOiAi2YTZiNis2LPYqtmK2YMg2YjYtNit2YYiLAp9OwpmdW5jdGlvbiBzZWN0b3JMYWJlbChjb2RlKSB7IHJldHVybiBTRUNUT1JfQVJbY29kZV0gfHwgY29kZTsgfQoKLy8gLS0tLS0tLS0tLSBuZXcgY2FtcGFpZ24gLS0tLS0tLS0tLQpmdW5jdGlvbiByZW5kZXJOZXdDYW1wYWlnbigpIHsKICB0cGxJbnRvKCJ0cGwtbmV3LWNhbXBhaWduIik7CiAgJCgiI2JhY2tCdG4iKS5hZGRFdmVudExpc3RlbmVyKCJjbGljayIsIHJlbmRlckNhbXBhaWducyk7CiAgJCgidGV4dGFyZWFbbmFtZT1jb3Zlcl9sZXR0ZXJfYXJdIikudmFsdWUgPSBERUZBVUxUX0FSOwogICQoInRleHRhcmVhW25hbWU9Y292ZXJfbGV0dGVyX2VuXSIpLnZhbHVlID0gREVGQVVMVF9FTjsKICAvLyBMb2FkIHNlY3RvcnMgZnJvbSAvYXBpL3NlY3RvcnMgYW5kIHBvcHVsYXRlIGRyb3Bkb3duCiAgKGFzeW5jICgpID0+IHsKICAgIGNvbnN0IHNlbCA9ICQoIiNzZWN0b3JTZWxlY3QiKTsKICAgIHRyeSB7CiAgICAgIGNvbnN0IHIgPSBhd2FpdCBmZXRjaCgiL2FwaS9zZWN0b3JzIik7CiAgICAgIGlmICghci5vaykgdGhyb3cgbmV3IEVycm9yKCJzZWN0b3JzIGZldGNoIGZhaWxlZCIpOwogICAgICBjb25zdCB7IHNlY3RvcnMgfSA9IGF3YWl0IHIuanNvbigpOwogICAgICBzZWwuaW5uZXJIVE1MID0gIiI7CiAgICAgIGZvciAoY29uc3QgcyBvZiBzZWN0b3JzKSB7CiAgICAgICAgY29uc3Qgb3B0ID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgib3B0aW9uIik7CiAgICAgICAgb3B0LnZhbHVlID0gcy5jb2RlOwogICAgICAgIG9wdC50ZXh0Q29udGVudCA9IGAke3MubGFiZWxfYXJ9ICgke3MuY291bnR9INi02LHZg9ipKWA7CiAgICAgICAgaWYgKHMuY291bnQgPT09IDApIG9wdC5kaXNhYmxlZCA9IHRydWU7CiAgICAgICAgc2VsLmFwcGVuZENoaWxkKG9wdCk7CiAgICAgIH0KICAgICAgaWYgKCFzZWN0b3JzLmxlbmd0aCkgewogICAgICAgIHNlbC5pbm5lckhUTUwgPSAnPG9wdGlvbiB2YWx1ZT0iIj7ZhNinINiq2YjYrNivINiq2K7Ytdi12KfYqi4g2KPYttmBINi02LHZg9in2Kog2KPZiNmE2KfZiy48L29wdGlvbj4nOwogICAgICB9CiAgICB9IGNhdGNoIChlKSB7CiAgICAgIHNlbC5pbm5lckhUTUwgPSAnPG9wdGlvbiB2YWx1ZT0iIj7Yqti52LDZkdixINiq2K3ZhdmK2YQg2KfZhNiq2K7Ytdi12KfYqjwvb3B0aW9uPic7CiAgICB9CiAgfSkoKTsKCiAgJCgiI25ld0NhbXBGb3JtIikuYWRkRXZlbnRMaXN0ZW5lcigic3VibWl0IiwgYXN5bmMgKGUpID0+IHsKICAgIGUucHJldmVudERlZmF1bHQoKTsKICAgIGNvbnN0IGZkID0gbmV3IEZvcm1EYXRhKGUudGFyZ2V0KTsKICAgIGNvbnN0IGVyckJveCA9ICQoIiNuZXdFcnIiKTsKICAgIGNvbnN0IHByb2cgPSAkKCIjbmV3UHJvZ3Jlc3MiKTsKICAgIGVyckJveC50ZXh0Q29udGVudCA9ICIiOyBwcm9nLmNsYXNzTGlzdC5yZW1vdmUoImhpZGRlbiIpOwogICAgJCgiI2NyZWF0ZUJ0biIpLmRpc2FibGVkID0gdHJ1ZTsKCiAgICBjb25zdCBjdiA9IGZkLmdldCgiY3YiKTsKICAgIGlmICghY3YgfHwgIWN2LnNpemUpIHsgZXJyQm94LnRleHRDb250ZW50ID0gItin2K7YqtixINmF2YTZgSBDVi4iOyByZXNldCgpOyByZXR1cm47IH0KICAgIGlmIChjdi5zaXplID4gMTAgKiAxMDI0ICogMTAyNCkgeyBlcnJCb3gudGV4dENvbnRlbnQgPSAi2KfZhNmF2YTZgSDZg9io2YrYsSDYrNiv2YvYpyAoMTBNQiDYrdivINij2YLYtdmJKS4iOyByZXNldCgpOyByZXR1cm47IH0KCiAgICB0cnkgewogICAgICAvLyAxKSB1cGxvYWQgQ1YKICAgICAgcHJvZy50ZXh0Q29udGVudCA9ICLYrNin2LHZiiDYsdmB2Lkg2KfZhNmAIENWLi4uIjsKICAgICAgY29uc3QgdXAgPSBhd2FpdCBmZXRjaCgiL2FwaS91cGxvYWQiLCB7CiAgICAgICAgbWV0aG9kOiAiUE9TVCIsCiAgICAgICAgaGVhZGVyczogeyAiQ29udGVudC1UeXBlIjogImFwcGxpY2F0aW9uL3BkZiIsICJYLUZpbGVuYW1lIjogY3YubmFtZSB9LAogICAgICAgIGJvZHk6IGN2LAogICAgICB9KTsKICAgICAgaWYgKHVwLnN0YXR1cyA9PT0gNDAxKSByZXR1cm4gcmVuZGVyTG9naW4oKTsKICAgICAgY29uc3QgdXBEYXRhID0gYXdhaXQgdXAuanNvbigpOwogICAgICBpZiAoIXVwLm9rKSB0aHJvdyBuZXcgRXJyb3IodXBEYXRhLmVycm9yIHx8ICLZgdi02YQg2LHZgdi5IENWIik7CgogICAgICAvLyAyKSBjcmVhdGUgY2FtcGFpZ24KICAgICAgcHJvZy50ZXh0Q29udGVudCA9ICLYrNin2LHZiiDYpdmG2LTYp9ihINin2YTYrdmF2YTYqSDZiNiq2KzZh9mK2LIg2KfZhNi02LHZg9in2KouLi4iOwogICAgICBjb25zdCBib2R5ID0gewogICAgICAgIGN1c3RvbWVyX2xhYmVsOiBmZC5nZXQoImN1c3RvbWVyX2xhYmVsIiksCiAgICAgICAgY3Zfc3RvcmFnZV9wYXRoOiB1cERhdGEucGF0aCwKICAgICAgICBzZW5kZXJfbmFtZTogZmQuZ2V0KCJzZW5kZXJfbmFtZSIpLAogICAgICAgIHN1YmplY3RfYXI6IGZkLmdldCgic3ViamVjdF9hciIpLAogICAgICAgIHN1YmplY3RfZW46IGZkLmdldCgic3ViamVjdF9lbiIpLAogICAgICAgIGNvdmVyX2xldHRlcl9hcjogZmQuZ2V0KCJjb3Zlcl9sZXR0ZXJfYXIiKSwKICAgICAgICBjb3Zlcl9sZXR0ZXJfZW46IGZkLmdldCgiY292ZXJfbGV0dGVyX2VuIiksCiAgICAgICAgdXNlX2FpOiAhIWZkLmdldCgidXNlX2FpIiksCiAgICAgICAgcGFja2FnZV9zaXplOiBmZC5nZXQoInBhY2thZ2Vfc2l6ZSIpID09PSAiMCIgPyAiYWxsIiA6IGZkLmdldCgicGFja2FnZV9zaXplIiksCiAgICAgICAgdGFyZ2V0X3NlY3RvcjogZmQuZ2V0KCJ0YXJnZXRfc2VjdG9yIikgfHwgImFueSIsCiAgICAgIH07CiAgICAgIGNvbnN0IGNyID0gYXdhaXQgZmV0Y2goIi9hcGkvY2FtcGFpZ25zIiwgewogICAgICAgIG1ldGhvZDogIlBPU1QiLAogICAgICAgIGhlYWRlcnM6IHsgIkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiB9LAogICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KGJvZHkpLAogICAgICB9KTsKICAgICAgY29uc3QgY3JEYXRhID0gYXdhaXQgY3IuanNvbigpOwogICAgICBpZiAoIWNyLm9rKSB0aHJvdyBuZXcgRXJyb3IoY3JEYXRhLmVycm9yIHx8ICLZgdi02YQg2KXZhti02KfYoSDYp9mE2K3ZhdmE2KkiKTsKCiAgICAgIC8vIFNob3cgb3ZlcmxhcCB3YXJuaW5nIGJyaWVmbHkgaWYgdGhlIHBvb2wgd2FzIGV4aGF1c3RlZC4KICAgICAgaWYgKGNyRGF0YS5vdmVybGFwICYmIGNyRGF0YS5vdmVybGFwID4gMCkgewogICAgICAgIGFsZXJ0KAogICAgICAgICAgYNiq2YbYqNmK2Yc6INiq2YUg2KfYrtiq2YrYp9ixICR7Y3JEYXRhLnRhcmdldGVkfSDYtNix2YPYqdiMINmF2YbZh9inICR7Y3JEYXRhLm92ZXJsYXB9IGAgKwogICAgICAgICAgYNi02LHZg9ipINmF2Y/Yudin2K8g2KfYs9iq2K7Yr9in2YXZh9inICjZg9in2YbYqiDYttmF2YYg2K3ZhdmE2KfYqiDYs9in2KjZgtipKS4g2KfZhNi02LHZg9in2Kog2KfZhNis2K/Zitiv2Kkg2YTZhSDYqtmD2YHZkCDYp9mE2KjYp9mC2KkuYAogICAgICAgICk7CiAgICAgIH0KICAgICAgcmVuZGVyQ2FtcGFpZ25EZXRhaWwoY3JEYXRhLmNhbXBhaWduLmlkKTsKICAgIH0gY2F0Y2ggKGVycikgewogICAgICBlcnJCb3gudGV4dENvbnRlbnQgPSBlcnIubWVzc2FnZSB8fCAi2K3Yr9irINiu2LfYoy4iOwogICAgICByZXNldCgpOwogICAgfQogICAgZnVuY3Rpb24gcmVzZXQoKSB7IHByb2cuY2xhc3NMaXN0LmFkZCgiaGlkZGVuIik7ICQoIiNjcmVhdGVCdG4iKS5kaXNhYmxlZCA9IGZhbHNlOyB9CiAgfSk7Cn0KCi8vIC0tLS0tLS0tLS0gY2FtcGFpZ24gZGV0YWlsIC0tLS0tLS0tLS0KYXN5bmMgZnVuY3Rpb24gcmVuZGVyQ2FtcGFpZ25EZXRhaWwoaWQpIHsKICB0cGxJbnRvKCJ0cGwtY2FtcGFpZ24tZGV0YWlsIik7CiAgJCgiI2JhY2tCdG4iKS5hZGRFdmVudExpc3RlbmVyKCJjbGljayIsIHJlbmRlckNhbXBhaWducyk7CiAgJCQoIi5zdGF0dXMtcm93IFtkYXRhLWFjdF0iKS5mb3JFYWNoKGJ0biA9PiB7CiAgICBidG4uYWRkRXZlbnRMaXN0ZW5lcigiY2xpY2siLCAoKSA9PiBjaGFuZ2VTdGF0dXMoaWQsIGJ0bi5kYXRhc2V0LmFjdCkpOwogIH0pOwogICQoIiNyZWZyZXNoU3RhdHMiKS5hZGRFdmVudExpc3RlbmVyKCJjbGljayIsICgpID0+IGxvYWREZXRhaWwoaWQpKTsKICBhd2FpdCBsb2FkRGV0YWlsKGlkKTsKfQoKYXN5bmMgZnVuY3Rpb24gbG9hZERldGFpbChpZCkgewogIHRyeSB7CiAgICAvLyBnZXQgY2FtcGFpZ24gbWV0YQogICAgY29uc3QgciA9IGF3YWl0IGZldGNoKCIvYXBpL2NhbXBhaWducyIpOwogICAgaWYgKHIuc3RhdHVzID09PSA0MDEpIHJldHVybiByZW5kZXJMb2dpbigpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHIuanNvbigpOwogICAgY29uc3QgYyA9IChkYXRhLmNhbXBhaWducyB8fCBbXSkuZmluZCh4ID0+IHguaWQgPT09IGlkKTsKICAgIGlmICghYykgeyBhcHAuaW5uZXJIVE1MID0gJzxkaXYgY2xhc3M9ImNhcmQiPtin2YTYrdmF2YTYqSDYutmK2LEg2YXZiNis2YjYr9ipLjwvZGl2Pic7IHJldHVybjsgfQogICAgJCgiI2NkVGl0bGUiKS50ZXh0Q29udGVudCA9IGMuY3VzdG9tZXJfbGFiZWw7CiAgICBjb25zdCBzdCA9ICQoIiNjZFN0YXR1cyIpOwogICAgc3QuY2xhc3NOYW1lID0gInBpbGwgIiArIGMuc3RhdHVzOyBzdC50ZXh0Q29udGVudCA9IHN0YXR1c0FyKGMuc3RhdHVzKTsKCiAgICAvLyBzdGF0cwogICAgY29uc3Qgc3IgPSBhd2FpdCBmZXRjaChgL2FwaS9zdGF0cz9jYW1wYWlnbl9pZD0ke2lkfWApOwogICAgY29uc3Qgc2QgPSBhd2FpdCBzci5qc29uKCk7CiAgICBjb25zdCBjb3VudHMgPSBzZC5jb3VudHMgfHwge307CiAgICBjb25zdCBzZW50ID0gY291bnRzLnNlbnQgfHwgMCwgZmFpbGVkID0gY291bnRzLmZhaWxlZCB8fCAwOwogICAgY29uc3QgcGVuZGluZyA9IGNvdW50cy5wZW5kaW5nIHx8IDAsIHRvdGFsID0gY291bnRzLnRvdGFsIHx8IDA7CiAgICBjb25zdCBvcGVuZWQgPSAoc2Qub3BlbnMgfHwgW10pLmxlbmd0aDsKCiAgICAkKCIjY2RDb3VudHMiKS5pbm5lckhUTUwgPSBgCiAgICAgICR7Y2VsbCgi2KfZhNil2KzZhdin2YTZiiIsIHRvdGFsKX0KICAgICAgJHtjZWxsKCLZhdmP2LHYs9mO2YQiLCBzZW50KX0KICAgICAgJHtjZWxsKCLZgdi02YQiLCBmYWlsZWQpfQogICAgICAke2NlbGwoItmF2KrYqNmC2Y0iLCBwZW5kaW5nKX0KICAgICAgJHtjZWxsKCLZgdmP2KrYrSIsIG9wZW5lZCl9CiAgICBgOwogICAgY29uc3QgcGN0ID0gdG90YWwgPyBNYXRoLnJvdW5kKCgoc2VudCArIGZhaWxlZCkgLyB0b3RhbCkgKiAxMDApIDogMDsKICAgICQoIiNjZEJhciIpLnN0eWxlLndpZHRoID0gcGN0ICsgIiUiOwoKICAgIGNvbnN0IG9wZW5zQm94ID0gJCgiI2NkT3BlbnMiKTsKICAgIGlmICghc2Qub3BlbnMgfHwgIXNkLm9wZW5zLmxlbmd0aCkgb3BlbnNCb3gudGV4dENvbnRlbnQgPSAi2YTZhSDYqtmP2LHYtdivINmB2KrYrdin2Kog2KjYudivLiI7CiAgICBlbHNlIHsKICAgICAgb3BlbnNCb3guaW5uZXJIVE1MID0gIiI7CiAgICAgIGZvciAoY29uc3QgbyBvZiBzZC5vcGVucykgewogICAgICAgIGNvbnN0IGQgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCJkaXYiKTsgZC5jbGFzc05hbWUgPSAib3Blbi1pdGVtIjsKICAgICAgICBkLmlubmVySFRNTCA9IGA8c3Bhbj4ke2VzYyhvLmNvbXBhbnlfbmFtZSl9PC9zcGFuPgogICAgICAgICAgPHNwYW4gY2xhc3M9Im1ldGEiPiR7by5vcGVuX2NvdW50fcOXIMK3ICR7c2hvcnREYXRlKG8uZmlyc3Rfb3Blbl9hdCl9PC9zcGFuPmA7CiAgICAgICAgb3BlbnNCb3guYXBwZW5kQ2hpbGQoZCk7CiAgICAgIH0KICAgIH0KICB9IGNhdGNoIChlKSB7CiAgICBjb25zb2xlLmVycm9yKGUpOwogIH0KfQoKYXN5bmMgZnVuY3Rpb24gY2hhbmdlU3RhdHVzKGlkLCBzdGF0dXMpIHsKICBhd2FpdCBmZXRjaChgL2FwaS9jYW1wYWlnbnM/aWQ9JHtpZH1gLCB7CiAgICBtZXRob2Q6ICJQQVRDSCIsCiAgICBoZWFkZXJzOiB7ICJDb250ZW50LVR5cGUiOiAiYXBwbGljYXRpb24vanNvbiIgfSwKICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsgc3RhdHVzIH0pLAogIH0pOwogIGxvYWREZXRhaWwoaWQpOwp9CgovLyAtLS0tLS0tLS0tIHV0aWxzIC0tLS0tLS0tLS0KY29uc3QgY2VsbCA9IChsLCB2KSA9PiBgPGRpdiBjbGFzcz0iY291bnQtY2VsbCI+PGRpdiBjbGFzcz0idiI+JHt2fTwvZGl2PjxkaXYgY2xhc3M9ImwiPiR7bH08L2Rpdj48L2Rpdj5gOwpjb25zdCBlc2MgPSAocykgPT4gU3RyaW5nKHMgPz8gIiIpLnJlcGxhY2UoL1smPD4iJ10vZywgbSA9PiAoewogICImIjoiJmFtcDsiLCI8IjoiJmx0OyIsIj4iOiImZ3Q7IiwnIic6IiZxdW90OyIsIiciOiImIzM5OyJ9W21dKSk7CmNvbnN0IHNob3J0RGF0ZSA9IChpc28pID0+IGlzbyA/IG5ldyBEYXRlKGlzbykudG9Mb2NhbGVTdHJpbmcoImFyIikgOiAi4oCUIjsKCmluaXQoKTsK"

# ─── Static file routes ───────────────────────────────────────────────────────

@app.route("/")
@app.route("/index.html")
def index():
    return Response(
        _b64.b64decode(_STATIC_INDEX_HTML),
        mimetype="text/html; charset=utf-8",
    )


@app.route("/style.css")
def stylecss():
    return Response(
        _b64.b64decode(_STATIC_STYLE_CSS),
        mimetype="text/css; charset=utf-8",
    )


@app.route("/app.js")
def appjs():
    return Response(
        _b64.b64decode(_STATIC_APP_JS),
        mimetype="application/javascript; charset=utf-8",
    )


# ─── Auth ────────────────────────────────────────────────────────────────────

COOKIE_NAME = "elmy_auth"
COOKIE_TTL_DAYS = 7
ONE_PIXEL_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


def _auth_secret() -> str:
    return os.environ.get("SITE_PASSWORD", "") + "|elmy-cv-bot|v1"


def _make_auth_token() -> str:
    expires_at = int(time.time()) + COOKIE_TTL_DAYS * 86400
    payload = str(expires_at)
    sig = hmac.new(_auth_secret().encode(), payload.encode(),
                   hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _is_authed() -> bool:
    cookie_val = request.cookies.get(COOKIE_NAME, "")
    if not cookie_val:
        return False
    try:
        payload, sig = cookie_val.split(".", 1)
        expires_at = int(payload)
    except (ValueError, AttributeError):
        return False
    if expires_at < time.time():
        return False
    expected = hmac.new(_auth_secret().encode(), payload.encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _require_auth():
    if not _is_authed():
        return jsonify({"error": "unauthorized"}), 401
    return None


def _db() -> SupabaseDB:
    return SupabaseDB()


# ─── /api/login ──────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST", "DELETE"])
def login():
    if request.method == "DELETE":
        resp = make_response(jsonify({"ok": True}))
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp
    body = request.get_json(force=True, silent=True) or {}
    provided = (body.get("password") or "").strip()
    expected = os.environ.get("SITE_PASSWORD", "")
    if not expected:
        return jsonify({"error": "SITE_PASSWORD not configured"}), 500
    if provided != expected:
        return jsonify({"error": "wrong password"}), 401
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(COOKIE_NAME, _make_auth_token(),
                    max_age=COOKIE_TTL_DAYS * 86400,
                    httponly=True, samesite="Lax", secure=True, path="/")
    return resp


# ─── /api/me ─────────────────────────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
def me():
    if _is_authed():
        return jsonify({"authed": True})
    return jsonify({"authed": False}), 401


# ─── /api/campaigns ──────────────────────────────────────────────────────────

@app.route("/api/campaigns", methods=["GET", "POST", "PATCH"])
def campaigns():
    err = _require_auth()
    if err:
        return err
    try:
        db = _db()
        if request.method == "GET":
            camps = db.list_campaigns()
            out = [{**c, "counts": db.campaign_counts(c["id"])} for c in camps]
            return jsonify({"campaigns": out})

        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}
            required = ("customer_label", "cv_storage_path", "sender_name",
                        "subject_ar", "subject_en", "cover_letter_ar",
                        "cover_letter_en")
            missing = [k for k in required if not body.get(k)]
            if missing:
                return jsonify({"error": "missing fields", "fields": missing}), 400
            pkg_raw = body.get("package_size")
            if pkg_raw in (None, "", "all"):
                pkg = None
            else:
                try:
                    pkg = int(pkg_raw)
                    if pkg <= 0:
                        pkg = None
                except (TypeError, ValueError):
                    return jsonify({"error": "package_size must be a positive integer or 'all'"}), 400
            sector_raw = body.get("target_sector")
            sector = (sector_raw.strip()
                      if isinstance(sector_raw, str)
                      and sector_raw.strip()
                      and sector_raw.strip().lower() != "any"
                      else None)
            camp = db.create_campaign(
                customer_label=body["customer_label"],
                cv_storage_path=body["cv_storage_path"],
                sender_name=body["sender_name"],
                subject_ar=body["subject_ar"],
                subject_en=body["subject_en"],
                cover_letter_ar=body["cover_letter_ar"],
                cover_letter_en=body["cover_letter_en"],
                use_ai=bool(body.get("use_ai", True)),
                package_size=pkg,
                target_sector=sector,
            )
            result = db.populate_campaign_sends(
                camp["id"], package_size=pkg, target_sector=sector
            )
            return jsonify({
                "campaign": camp,
                "targeted": result["targeted"],
                "overlap": result["overlap"],
            })

        # PATCH
        cid_str = request.args.get("id", "")
        try:
            cid = int(cid_str)
        except ValueError:
            return jsonify({"error": "bad id"}), 400
        body = request.get_json(force=True, silent=True) or {}
        status = (body.get("status") or "").strip()
        valid = {"active", "paused", "stopped", "done", "draft"}
        if status not in valid:
            return jsonify({"error": f"status must be one of {sorted(valid)}"}), 400
        db.set_campaign_status(cid, status)
        return jsonify({"ok": True, "id": cid, "status": status})

    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/companies ──────────────────────────────────────────────────────────

@app.route("/api/companies", methods=["GET", "POST"])
def companies():
    err = _require_auth()
    if err:
        return err
    try:
        db = _db()
        if request.method == "GET":
            rows = db.list_companies(limit=5000)
            return jsonify({"companies": rows, "count": len(rows)})
        body = request.get_json(force=True, silent=True) or {}
        rows = body if isinstance(body, list) else body.get("companies") or []
        if not rows:
            return jsonify({"error": "no companies provided"}), 400
        clean = [r for r in rows if r.get("company_name") and r.get("email")]
        db.upsert_companies(clean)
        return jsonify({"submitted": len(clean), "skipped": len(rows) - len(clean)})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/sectors ────────────────────────────────────────────────────────────

SECTOR_LABELS = {
    "Healthcare": "صحة",
    "Marketing": "تسويق وإعلان",
    "Technology": "تقنية وبرمجة",
    "Finance": "مالية وبنوك",
    "Engineering": "هندسة ومقاولات",
    "Legal": "قانون",
    "Retail": "تجزئة وتجارة",
    "Education": "تعليم",
    "HR": "موارد بشرية",
    "Hospitality": "ضيافة وفنادق",
    "Logistics": "لوجستيك وشحن",
}


@app.route("/api/sectors", methods=["GET"])
def sectors():
    err = _require_auth()
    if err:
        return err
    try:
        db = _db()
        rows = db._select("/companies?select=sector&limit=100000")
        counts: dict[str, int] = {}
        for r in rows:
            s = (r.get("sector") or "").strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
        result = [
            {"code": code, "label_ar": SECTOR_LABELS.get(code, code),
             "count": counts.get(code, 0)}
            for code in SECTOR_LABELS
        ]
        for code in sorted(counts.keys()):
            if code not in SECTOR_LABELS:
                result.append({"code": code, "label_ar": code,
                                "count": counts[code]})
        return jsonify({"sectors": result})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/upload ─────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    err = _require_auth()
    if err:
        return err
    MAX_BYTES = 10 * 1024 * 1024
    data = request.get_data()
    if not data or len(data) > MAX_BYTES:
        return jsonify({"error": "file too large or empty", "max_mb": 10}), 413
    if not data.startswith(b"%PDF"):
        return jsonify({"error": "not a PDF (must start with %PDF)"}), 400
    filename = (request.headers.get("X-Filename") or "cv.pdf").strip()
    try:
        db = _db()
        path = db.upload_cv(data, filename)
        return jsonify({"path": path, "size": len(data)})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/stats ──────────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def stats():
    err = _require_auth()
    if err:
        return err
    cid_str = request.args.get("campaign_id", "")
    try:
        cid = int(cid_str)
    except ValueError:
        return jsonify({"error": "bad campaign_id"}), 400
    try:
        db = _db()
        counts = db.campaign_counts(cid)
        opens = db.campaign_opens(cid, limit=100)
        return jsonify({"counts": counts, "opens": opens})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/tick ───────────────────────────────────────────────────────────────

@app.route("/api/tick", methods=["GET"])
def tick():
    from bot.web_engine import run_tick
    provided = (request.args.get("token") or "").strip()
    expected = os.environ.get("CRON_TOKEN", "")
    if not expected or provided != expected:
        return jsonify({"error": "forbidden"}), 403
    try:
        db = _db()
        result = run_tick(
            db,
            gmail_address=os.environ.get("GMAIL_ADDRESS", ""),
            app_password=os.environ.get("GMAIL_APP_PASSWORD", ""),
            pixel_base_url=os.environ.get("PIXEL_BASE_URL", ""),
            pixel_token=os.environ.get("PIXEL_TOKEN", ""),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        )
        return jsonify({
            "action": result.action,
            "reason": result.reason,
            "campaign_id": result.campaign_id,
            "company": result.company,
            "source": result.source,
            "sent_today": result.sent_today,
            "daily_cap": result.daily_cap,
        })
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/pixel ──────────────────────────────────────────────────────────────

@app.route("/api/pixel", methods=["GET"])
def pixel():
    uid = (request.args.get("id") or "").strip()
    if uid:
        try:
            db = _db()
            db._post("/email_opens", {
                "email_uuid": uid,
                "ip": request.remote_addr or "",
                "user_agent": request.headers.get("User-Agent", ""),
            })
        except Exception:
            pass
    return Response(
        ONE_PIXEL_GIF,
        mimetype="image/gif",
        headers={"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"},
    )


# ─── /api/import ─────────────────────────────────────────────────────────────

@app.route("/api/import", methods=["POST"])
def import_companies():
    """Accept an Excel (.xlsx) upload and upsert companies into Supabase."""
    err = _require_auth()
    if err:
        return err
    data = request.get_data()
    if not data:
        return jsonify({"error": "no file received"}), 400
    if len(data) > 20 * 1024 * 1024:
        return jsonify({"error": "file too large (max 20 MB)"}), 413

    # Write to a temp file so openpyxl can read it
    import tempfile, os
    suffix = ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        from bot.excel_reader import read_companies
        result = read_companies(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if not result.recipients and result.errors:
        return jsonify({"error": result.errors[0], "all_errors": result.errors}), 400

    if result.recipients:
        try:
            db = _db()
            db.upsert_companies(result.recipients)
        except SupabaseError as exc:
            return jsonify({"error": str(exc)}), 500

    return jsonify({
        "imported": len(result.recipients),
        "skipped": result.error_count,
        "errors": result.errors[:10],   # first 10 row errors if any
    })
