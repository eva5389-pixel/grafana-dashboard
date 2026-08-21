#!/usr/bin/env python3
"""Build a color-coded card layout from the main mutual-fund dashboard."""

from copy import deepcopy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dashboards" / "mutual-funds.json"
DESTINATION = ROOT / "dashboards" / "mutual-funds-cards.json"

GROUPS = [
    ("精選總覽", "🟨", "#D9A400", [2]),
    ("區域市場", "🟦", "#3274D9", list(range(3, 13))),
    ("收益與防禦", "🟩", "#56A64B", [13, 22, 23]),
    ("商品與資源", "🟧", "#E0752D", [14, 15, 16]),
    ("創新科技", "🟪", "#8F3BB8", [17, 18, 19, 20, 21]),
    ("磷化銦專區", "🟦", "#00A6A6", [1001, 1002]),
]

# Each card gets its own visual identity. The exact hex color is also applied
# to the ranking cells, so markets remain distinguishable beyond the emoji.
PANEL_COLORS = {
    2: ("🟨", "#D9A400"),
    3: ("🟥", "#E53935"),       # Taiwan
    4: ("🌸", "#D81B60"),       # Japan
    5: ("🟪", "#8E24AA"),       # Korea
    6: ("🔵", "#5E35B1"),       # Hong Kong
    7: ("🟦", "#3949AB"),       # China
    8: ("🔷", "#1E88E5"),       # United States
    9: ("🟦", "#00ACC1"),       # India
    10: ("🟩", "#00897B"),      # ASEAN
    11: ("🟢", "#43A047"),      # Europe
    12: ("🟨", "#F9A825"),      # Brazil
    13: ("🟩", "#2E7D32"),
    14: ("🟧", "#EF6C00"),
    15: ("🟨", "#FBC02D"),
    16: ("🟫", "#8D6E63"),
    17: ("🟪", "#7B1FA2"),
    18: ("🟦", "#1565C0"),
    19: ("🟧", "#F4511E"),
    20: ("🔷", "#00838F"),
    21: ("🟣", "#6A1B9A"),
    22: ("🟩", "#388E3C"),
    23: ("🟥", "#C62828"),
    1001: ("💠", "#00A6A6"),
    1002: ("💠", "#00A6A6"),
}


def section_panel(panel_id: int, title: str, icon: str, color: str, y: int) -> dict:
    return {
        "id": panel_id,
        "type": "text",
        "title": "",
        "transparent": True,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 2},
        "options": {
            "mode": "html",
            "content": (
                f'<div style="background:{color};color:white;padding:12px 18px;'
                f'border-radius:10px;font-size:22px;font-weight:700">{icon} {title}</div>'
            ),
        },
    }


def recolor_rank(panel: dict, color: str) -> None:
    if panel.get("type") != "table":
        return
    overrides = panel.setdefault("fieldConfig", {}).setdefault("overrides", [])
    overrides[:] = [
        item for item in overrides
        if not (item.get("matcher", {}).get("id") == "byName" and item.get("matcher", {}).get("options") == "rank")
    ]
    mappings = {str(rank): {"color": color, "text": f"👑 {rank}" if rank == 1 else str(rank)} for rank in range(1, 11)}
    overrides.insert(0, {
        "matcher": {"id": "byName", "options": "rank"},
        "properties": [
            {"id": "custom.cellOptions", "value": {"type": "color-background"}},
            {"id": "mappings", "value": [{"type": "value", "options": mappings}]},
        ],
    })


dashboard = json.loads(SOURCE.read_text(encoding="utf-8"))
by_id = {panel["id"]: panel for panel in dashboard["panels"]}
panels = []

hero = deepcopy(by_id[1])
hero["id"] = 2000
hero["title"] = "全球共同基金策略平台｜卡牌分類版"
hero["gridPos"] = {"x": 0, "y": 0, "w": 24, "h": 10}
hero["options"]["content"] = (
    "# 全球共同基金策略平台｜卡牌分類版\n"
    "以色彩區分市場屬性：🟨精選、🟦區域、🟩收益防禦、🟧商品資源、🟪創新科技、🔷磷化銦。\n\n"
    + by_id[1]["options"]["content"].split("\n\n", 1)[1]
)
panels.append(hero)

y = 10
next_id = 2100
for group_name, icon, color, ids in GROUPS:
    panels.append(section_panel(next_id, group_name, icon, color, y))
    next_id += 1
    y += 2
    cards = []
    for panel_id in ids:
        panel = deepcopy(by_id[panel_id])
        panel["id"] = next_id
        next_id += 1
        card_icon, card_color = PANEL_COLORS.get(panel_id, (icon, color))
        panel["title"] = f"{card_icon} {panel['title']}"
        panel["transparent"] = False
        recolor_rank(panel, card_color)
        cards.append(panel)

    if group_name == "磷化銦專區":
        cards[0]["gridPos"] = {"x": 0, "y": y, "w": 16, "h": 9}
        cards[1]["gridPos"] = {"x": 16, "y": y, "w": 8, "h": 9}
        panels.extend(cards)
        y += 9
        continue

    for index, panel in enumerate(cards):
        panel["gridPos"] = {"x": (index % 2) * 12, "y": y + (index // 2) * 9, "w": 12, "h": 9}
        panels.append(panel)
    y += ((len(cards) + 1) // 2) * 9

dashboard["panels"] = panels
dashboard["title"] = "全球共同基金策略平台｜卡牌分類版"
dashboard["uid"] = "global-mutual-fund-card-view"
dashboard["version"] = 1
dashboard["tags"] = sorted(set(dashboard.get("tags", []) + ["card-view", "color-groups"]))
DESTINATION.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(DESTINATION)
