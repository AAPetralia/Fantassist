# -*- coding: utf-8 -*-
"""
FANTASSIST — pipeline dati
Scarica statistiche giocatori (tabella pubblica fantacalcio.it),
classifica, calendario, rigoristi e indisponibili di Serie A,
e salva tutto come JSON nella cartella /data, pronta per la PWA.

Ogni fonte è indipendente: se una fallisce, le altre vengono
comunque aggiornate e il JSON precedente resta al suo posto.
"""

import io
import json
import re
import sys
import datetime as dt
from pathlib import Path

import requests
import pandas as pd

BASE = "https://www.fantacalcio.it"

CLASSIFICA_URL = f"{BASE}/serie-a/classifica"
CALENDARIO_URL = f"{BASE}/serie-a/calendario"
RIGORISTI_URL = f"{BASE}/rigoristi-serie-a"
INDISPONIBILI_URL = f"{BASE}/indisponibili-serie-a"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "
