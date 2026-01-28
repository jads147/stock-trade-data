import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Transaction:
    datum: datetime
    valuta: datetime
    betrag: float
    status: str
    verwendungszweck: str
    iban: str

    # Parsed fields
    typ: str = ""
    order_nr: str = ""
    isin: str = ""
    name: str = ""
    stueck: float = 0.0
    is_kauf: bool = False
    is_verkauf: bool = False


def parse_german_number(value: str) -> float:
    """Parse German number format (1.234,56 -> 1234.56)"""
    if not value or value.strip() == "":
        return 0.0
    # Remove thousand separators (.) and replace decimal comma with dot
    cleaned = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def format_german_number(value: float, decimals: int = 2) -> str:
    """Format number to German format (1234.56 -> 1.234,56)"""
    formatted = f"{value:,.{decimals}f}"
    # Swap . and , for German format
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted


def parse_german_date(value: str) -> datetime:
    """Parse German date format (DD.MM.YYYY)"""
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y")
    except ValueError:
        return datetime.min


def parse_verwendungszweck(zweck: str, transaction: Transaction):
    """Extract trade details from Verwendungszweck"""

    # Order pattern: Order Nr XXXXXX ISIN XXXXXXXXXXXX - Kauf/Verkauf (NAME ISIN XXX STK XX)
    order_match = re.search(r"Order Nr (\d+) ISIN ([A-Z0-9]{12}) - (Kauf|Verkauf)\s+\((.+?)\s+ISIN [A-Z0-9]{12}\s+STK\s+([\d,.\s]+)", zweck)
    if order_match:
        transaction.typ = "Order"
        transaction.order_nr = order_match.group(1)
        transaction.isin = order_match.group(2)
        transaction.is_kauf = order_match.group(3) == "Kauf"
        transaction.is_verkauf = order_match.group(3) == "Verkauf"
        transaction.name = order_match.group(4).strip()
        stueck_str = order_match.group(5).strip().replace(" ", "").replace("-", "")
        transaction.stueck = parse_german_number(stueck_str)
        return

    # Sparplan pattern
    sparplan_match = re.search(r"Sparplan-Order zu ISIN ([A-Z0-9]{12}) - (Kauf|Verkauf)\s+\((.+?)\s+ISIN [A-Z0-9]{12}\s+STK\s+([\d,.\s]+)", zweck)
    if sparplan_match:
        transaction.typ = "Sparplan"
        transaction.isin = sparplan_match.group(1)
        transaction.is_kauf = sparplan_match.group(2) == "Kauf"
        transaction.is_verkauf = sparplan_match.group(2) == "Verkauf"
        transaction.name = sparplan_match.group(3).strip()
        stueck_str = sparplan_match.group(4).strip().replace(" ", "").replace("-", "")
        transaction.stueck = parse_german_number(stueck_str)
        return

    # Bruchstücke pattern
    bruch_match = re.search(r"Bruchstücke-Order zu ISIN ([A-Z0-9]{12}) - (Kauf|Verkauf)\s+\((.+?)\s+ISIN [A-Z0-9]{12}\s+STK\s+([\d,.\s]+)", zweck)
    if bruch_match:
        transaction.typ = "Bruchstücke"
        transaction.isin = bruch_match.group(1)
        transaction.is_kauf = bruch_match.group(2) == "Kauf"
        transaction.is_verkauf = bruch_match.group(2) == "Verkauf"
        transaction.name = bruch_match.group(3).strip()
        stueck_str = bruch_match.group(4).strip().replace(" ", "").replace("-", "")
        transaction.stueck = parse_german_number(stueck_str)
        return

    # Gutschrift
    if "Gutschrift" in zweck:
        transaction.typ = "Einzahlung"
        return

    # Auszahlung
    if "Auszahlung" in zweck:
        transaction.typ = "Auszahlung"
        return

    # Lastschrift
    if "Lastschrift" in zweck:
        transaction.typ = "Lastschrift"
        return

    # Dividende
    if "Coupons/Dividende" in zweck:
        transaction.typ = "Dividende"
        div_match = re.search(r"ISIN ([A-Z0-9]{12})", zweck)
        if div_match:
            transaction.isin = div_match.group(1)
        return

    # Steuerausgleich
    if "Steuerausgleich" in zweck:
        transaction.typ = "Steuerausgleich"
        return

    # Vorabpauschale
    if "Vorabpauschale" in zweck:
        transaction.typ = "Vorabpauschale"
        vp_match = re.search(r"ISIN ([A-Z0-9]{12})", zweck)
        if vp_match:
            transaction.isin = vp_match.group(1)
        return

    # WP-Abrechnung (Knock-out etc.) - treat as sale
    if "WP-Abrechnung" in zweck:
        transaction.typ = "WP-Abrechnung"
        # Pattern: WP-Abrechnung Verkauf: NAME ISIN XXXXXXXXXXXX STK XX - REFERENZ
        wp_match = re.search(r"WP-Abrechnung Verkauf:.*?ISIN ([A-Z0-9]{12})\s+STK\s+([\d,.\s]+)", zweck)
        if wp_match:
            transaction.isin = wp_match.group(1)
            stueck_str = wp_match.group(2).strip().replace(" ", "").replace("-", "")
            transaction.stueck = parse_german_number(stueck_str)
            transaction.is_verkauf = True
        return

    # KKT-Abschluss
    if "KKT-Abschluss" in zweck:
        transaction.typ = "KKT-Abschluss"
        return

    transaction.typ = "Sonstig"


def read_csv(filepath: str) -> list[Transaction]:
    """Read and parse the CSV file"""
    transactions = []

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            t = Transaction(
                datum=parse_german_date(row.get("Datum", "")),
                valuta=parse_german_date(row.get("Valuta", "")),
                betrag=parse_german_number(row.get("Betrag", "")),
                status=row.get("Status", ""),
                verwendungszweck=row.get("Verwendungszweck", ""),
                iban=row.get("IBAN", "")
            )
            parse_verwendungszweck(t.verwendungszweck, t)
            transactions.append(t)

    return transactions


def generate_html(transactions: list[Transaction], output_path: str):
    """Generate HTML overview of trades"""

    # Calculate statistics - include Orders, Sparpläne, Bruchstücke, and WP-Abrechnungen
    trade_types = ["Order", "Sparplan", "Bruchstücke", "WP-Abrechnung"]
    trades = [t for t in transactions if t.typ in trade_types]
    einzahlungen = [t for t in transactions if t.typ == "Einzahlung"]
    auszahlungen = [t for t in transactions if t.typ == "Auszahlung"]
    steuerausgleich = [t for t in transactions if t.typ == "Steuerausgleich"]
    dividenden = [t for t in transactions if t.typ == "Dividende"]

    total_steuerausgleich = sum(t.betrag for t in steuerausgleich)
    total_dividenden = sum(t.betrag for t in dividenden)

    kaufe = [t for t in trades if t.is_kauf]
    verkaeufe = [t for t in trades if t.is_verkauf]

    total_kauf = sum(t.betrag for t in kaufe)
    total_verkauf = sum(t.betrag for t in verkaeufe)

    total_einzahlung = sum(t.betrag for t in einzahlungen)
    total_auszahlung = sum(t.betrag for t in auszahlungen)

    # Calculate trade volume statistics
    total_volume = sum(abs(t.betrag) for t in trades)
    total_trades_count = len(trades)

    # Volume per month
    volume_by_month = defaultdict(lambda: {"kauf": 0.0, "verkauf": 0.0, "count": 0})
    for t in trades:
        month_key = t.datum.strftime("%Y-%m")
        if t.is_kauf:
            volume_by_month[month_key]["kauf"] += abs(t.betrag)
        else:
            volume_by_month[month_key]["verkauf"] += abs(t.betrag)
        volume_by_month[month_key]["count"] += 1

    # P&L per month (will be calculated after pnl_events are generated)
    pnl_by_month = defaultdict(float)

    # Volume per weekday (0=Monday, 6=Sunday)
    volume_by_weekday = defaultdict(lambda: {"kauf": 0.0, "verkauf": 0.0, "count": 0})
    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    for t in trades:
        weekday = t.datum.weekday()
        if t.is_kauf:
            volume_by_weekday[weekday]["kauf"] += abs(t.betrag)
        else:
            volume_by_weekday[weekday]["verkauf"] += abs(t.betrag)
        volume_by_weekday[weekday]["count"] += 1

    # Group trades by ISIN with quantity tracking (Orders + Sparpläne + Bruchstücke)
    trades_by_isin = {}
    for t in trades:
        if not t.isin:  # Skip transactions without ISIN
            continue
        if t.isin not in trades_by_isin:
            trades_by_isin[t.isin] = {"name": t.name, "kaufe": [], "verkaeufe": []}
        if t.is_kauf:
            trades_by_isin[t.isin]["kaufe"].append(t)
        else:
            trades_by_isin[t.isin]["verkaeufe"].append(t)

    # Calculate PnL per ISIN - separate open and closed positions
    closed_positions = []
    open_positions = []

    for isin, data in trades_by_isin.items():
        kauf_sum = sum(t.betrag for t in data["kaufe"])
        verkauf_sum = sum(t.betrag for t in data["verkaeufe"])
        kauf_stueck = sum(t.stueck for t in data["kaufe"])
        verkauf_stueck = sum(t.stueck for t in data["verkaeufe"])

        # Calculate remaining/open quantity
        open_stueck = kauf_stueck - verkauf_stueck

        position_data = {
            "isin": isin,
            "name": data["name"],
            "kauf_count": len(data["kaufe"]),
            "verkauf_count": len(data["verkaeufe"]),
            "kauf_sum": kauf_sum,
            "verkauf_sum": verkauf_sum,
            "kauf_stueck": kauf_stueck,
            "verkauf_stueck": verkauf_stueck,
            "open_stueck": open_stueck,
        }

        if abs(open_stueck) < 0.001:  # Fully closed position
            position_data["pnl"] = verkauf_sum + kauf_sum
            # Calculate hold time (first buy to last sell)
            if data["kaufe"] and data["verkaeufe"]:
                first_buy = min(t.datum for t in data["kaufe"])
                last_sell = max(t.datum for t in data["verkaeufe"])
                position_data["hold_days"] = (last_sell - first_buy).days
                position_data["first_buy"] = first_buy
                position_data["last_sell"] = last_sell
            else:
                position_data["hold_days"] = 0
            # Calculate return %
            invested = abs(kauf_sum)
            position_data["rendite_pct"] = (position_data["pnl"] / invested * 100) if invested > 0 else 0
            closed_positions.append(position_data)
        else:
            # Open position - calculate average buy price for held shares
            if kauf_stueck > 0:
                avg_kauf_preis = abs(kauf_sum) / kauf_stueck
                position_data["avg_kauf_preis"] = avg_kauf_preis
                position_data["invested"] = open_stueck * avg_kauf_preis
            else:
                position_data["avg_kauf_preis"] = 0
                position_data["invested"] = 0

            # If there were partial sales, calculate realized PnL
            if verkauf_stueck > 0:
                # Proportional cost basis for sold shares
                cost_of_sold = (verkauf_stueck / kauf_stueck) * abs(kauf_sum) if kauf_stueck > 0 else 0
                position_data["realized_pnl"] = verkauf_sum - cost_of_sold
            else:
                position_data["realized_pnl"] = 0

            open_positions.append(position_data)

    # Sort closed by PnL, open by invested amount
    closed_positions.sort(key=lambda x: x["pnl"], reverse=True)
    open_positions.sort(key=lambda x: x.get("invested", 0), reverse=True)

    # Calculate totals using average cost basis (same method as P&L chart)
    cost_basis_calc = {}
    sorted_trades = sorted(trades, key=lambda t: t.datum)
    total_trade_pnl = 0.0

    for t in sorted_trades:
        if not t.isin:
            continue
        if t.isin not in cost_basis_calc:
            cost_basis_calc[t.isin] = {"cost": 0.0, "stueck": 0.0}
        basis = cost_basis_calc[t.isin]

        if t.is_kauf:
            basis["cost"] += abs(t.betrag)
            basis["stueck"] += t.stueck
        elif t.is_verkauf and t.stueck > 0 and basis["stueck"] > 0:
            avg_cost = basis["cost"] / basis["stueck"]
            cost_of_sold = avg_cost * t.stueck
            total_trade_pnl += t.betrag - cost_of_sold
            basis["cost"] -= cost_of_sold
            basis["stueck"] -= t.stueck

    total_realized_pnl = total_trade_pnl + total_steuerausgleich + total_dividenden
    total_invested_open = sum(p.get("invested", 0) for p in open_positions)

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Übersicht</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        /* Stats Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        .stat-label {{
            font-size: 0.85rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        .stat-value {{
            font-size: 1.8rem;
            font-weight: 700;
        }}
        .stat-value.positive {{ color: #10b981; }}
        .stat-value.negative {{ color: #ef4444; }}
        .stat-value.neutral {{ color: #00d4ff; }}

        /* Section */
        .section {{
            background: rgba(255,255,255,0.03);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.08);
        }}
        .section h2 {{
            font-size: 1.5rem;
            margin-bottom: 20px;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        /* Table */
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 14px 16px;
            text-align: left;
        }}
        th {{
            background: rgba(255,255,255,0.05);
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #888;
        }}
        th:first-child {{ border-radius: 10px 0 0 10px; }}
        th:last-child {{ border-radius: 0 10px 10px 0; }}
        tr:hover td {{
            background: rgba(255,255,255,0.03);
        }}
        td {{
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .text-right {{ text-align: right; }}
        .mono {{ font-family: 'SF Mono', Monaco, monospace; font-size: 0.9rem; }}
        .positive {{ color: #10b981; }}
        .negative {{ color: #ef4444; }}

        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-kauf {{
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }}
        .badge-verkauf {{
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
        }}

        .isin {{
            font-family: monospace;
            font-size: 0.8rem;
            color: #666;
        }}
        .name {{
            font-weight: 500;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        /* All trades table */
        .trades-table {{
            max-height: 600px;
            overflow-y: auto;
        }}
        .trades-table::-webkit-scrollbar {{
            width: 8px;
        }}
        .trades-table::-webkit-scrollbar-track {{
            background: rgba(255,255,255,0.05);
            border-radius: 4px;
        }}
        .trades-table::-webkit-scrollbar-thumb {{
            background: rgba(255,255,255,0.2);
            border-radius: 4px;
        }}

        /* Sortable table headers */
        th.sortable {{
            cursor: pointer;
            user-select: none;
            position: relative;
            padding-right: 24px;
            transition: background 0.2s;
        }}
        th.sortable:hover {{
            background: rgba(255,255,255,0.1);
        }}
        th.sortable::after {{
            content: '⇅';
            position: absolute;
            right: 8px;
            opacity: 0.4;
            font-size: 0.75rem;
        }}
        th.sortable.asc::after {{
            content: '↑';
            opacity: 1;
            color: #00d4ff;
        }}
        th.sortable.desc::after {{
            content: '↓';
            opacity: 1;
            color: #00d4ff;
        }}

        /* Chart container */
        .chart-container {{
            position: relative;
            height: 400px;
            margin-top: 20px;
        }}
        .chart-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }}
        @media (max-width: 1000px) {{
            .chart-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <h1>📈 Trade Übersicht</h1>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Einzahlungen</div>
                <div class="stat-value positive">{format_german_number(total_einzahlung)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Auszahlungen</div>
                <div class="stat-value negative">{format_german_number(total_auszahlung)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Realisierte P&L</div>
                <div class="stat-value {'positive' if total_realized_pnl >= 0 else 'negative'}">{'+' if total_realized_pnl >= 0 else ''}{format_german_number(total_realized_pnl)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Investiert (offen)</div>
                <div class="stat-value neutral">{format_german_number(total_invested_open)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Steuerausgleich</div>
                <div class="stat-value positive">+{format_german_number(total_steuerausgleich)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Dividenden</div>
                <div class="stat-value positive">+{format_german_number(total_dividenden)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Trade Volume (gesamt)</div>
                <div class="stat-value neutral">{format_german_number(total_volume)} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Anzahl Trades</div>
                <div class="stat-value neutral">{total_trades_count}</div>
            </div>
        </div>

        <div class="section">
            <h2>📊 Trade Volume</h2>
            <div style="margin-bottom: 15px;">
                <label style="display: inline-flex; align-items: center; cursor: pointer; color: #888; font-size: 0.9rem;">
                    <input type="checkbox" id="logScaleToggle" style="margin-right: 8px; cursor: pointer;">
                    Logarithmische Skala
                </label>
            </div>
            <div class="chart-grid">
                <div>
                    <h3 style="color: #888; font-size: 0.9rem; margin-bottom: 10px;">Volume pro Monat</h3>
                    <div class="chart-container">
                        <canvas id="volumeMonthChart"></canvas>
                    </div>
                </div>
                <div>
                    <h3 style="color: #888; font-size: 0.9rem; margin-bottom: 10px;">Volume pro Wochentag</h3>
                    <div class="chart-container">
                        <canvas id="volumeWeekdayChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📂 Offene Positionen (noch gehalten)</h2>
            <table id="open-positions-table">
                <thead>
                    <tr>
                        <th class="sortable" data-sort="string">ISIN</th>
                        <th class="sortable" data-sort="string">Name</th>
                        <th class="sortable text-right" data-sort="number">Stück</th>
                        <th class="sortable text-right" data-sort="number">Ø Kaufpreis</th>
                        <th class="sortable text-right" data-sort="number">Investiert</th>
                        <th class="sortable text-right" data-sort="number">Realisiert</th>
                    </tr>
                </thead>
                <tbody>
"""

    for item in open_positions:
        realized = item.get("realized_pnl", 0)
        realized_class = "positive" if realized >= 0 else "negative"
        realized_sign = "+" if realized >= 0 else ""
        html += f"""                    <tr>
                        <td class="isin">{item["isin"]}</td>
                        <td class="name" title="{item["name"]}">{item["name"][:40]}</td>
                        <td class="text-right mono">{format_german_number(item["open_stueck"])}</td>
                        <td class="text-right mono">{format_german_number(item.get("avg_kauf_preis", 0))} €</td>
                        <td class="text-right mono">{format_german_number(item.get("invested", 0))} €</td>
                        <td class="text-right mono {realized_class}">{realized_sign}{format_german_number(realized)} €</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>✅ Geschlossene Positionen</h2>
            <table id="closed-positions-table">
                <thead>
                    <tr>
                        <th class="sortable" data-sort="string">ISIN</th>
                        <th class="sortable" data-sort="string">Name</th>
                        <th class="sortable text-right" data-sort="number">Käufe</th>
                        <th class="sortable text-right" data-sort="number">Verkäufe</th>
                        <th class="sortable text-right" data-sort="number">Investiert</th>
                        <th class="sortable text-right" data-sort="number">Erlös</th>
                        <th class="sortable text-right" data-sort="number">P&L</th>
                    </tr>
                </thead>
                <tbody>
"""

    for item in closed_positions:
        pnl_class = "positive" if item["pnl"] >= 0 else "negative"
        pnl_sign = "+" if item["pnl"] >= 0 else ""
        html += f"""                    <tr>
                        <td class="isin">{item["isin"]}</td>
                        <td class="name" title="{item["name"]}">{item["name"][:40]}</td>
                        <td class="text-right mono">{item["kauf_count"]}</td>
                        <td class="text-right mono">{item["verkauf_count"]}</td>
                        <td class="text-right mono negative">{format_german_number(item["kauf_sum"])} €</td>
                        <td class="text-right mono positive">+{format_german_number(item["verkauf_sum"])} €</td>
                        <td class="text-right mono {pnl_class}">{pnl_sign}{format_german_number(item["pnl"])} €</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>📋 Alle Trades</h2>
            <div class="trades-table">
                <table id="all-trades-table">
                    <thead>
                        <tr>
                            <th class="sortable" data-sort="date">Datum</th>
                            <th class="sortable" data-sort="string">Typ</th>
                            <th class="sortable" data-sort="string">ISIN</th>
                            <th class="sortable" data-sort="string">Name</th>
                            <th class="sortable text-right" data-sort="number">Stück</th>
                            <th class="sortable text-right" data-sort="number">Betrag</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    for t in sorted(trades, key=lambda x: x.datum, reverse=True):
        typ_badge = "badge-kauf" if t.is_kauf else "badge-verkauf"
        typ_text = "Kauf" if t.is_kauf else "Verkauf"
        betrag_class = "negative" if t.betrag < 0 else "positive"
        betrag_sign = "" if t.betrag < 0 else "+"
        html += f"""                        <tr>
                            <td class="mono">{t.datum.strftime('%d.%m.%Y')}</td>
                            <td><span class="badge {typ_badge}">{typ_text}</span></td>
                            <td class="isin">{t.isin}</td>
                            <td class="name" title="{t.name}">{t.name[:35]}</td>
                            <td class="text-right mono">{format_german_number(t.stueck)}</td>
                            <td class="text-right mono {betrag_class}">{betrag_sign}{format_german_number(t.betrag)} €</td>
                        </tr>
"""

    html += """                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>📈 P&L Über Zeit</h2>
            <div class="chart-container" style="height: 450px;">
                <canvas id="pnlOverTimeChart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>📊 Trade Visualisierung - Geschlossene Positionen</h2>
            <div class="chart-grid">
                <div>
                    <h3 style="color: #888; font-size: 0.9rem; margin-bottom: 10px;">Haltedauer vs. Rendite (%)</h3>
                    <div class="chart-container">
                        <canvas id="holdTimePctChart"></canvas>
                    </div>
                </div>
                <div>
                    <h3 style="color: #888; font-size: 0.9rem; margin-bottom: 10px;">Haltedauer vs. Rendite (€)</h3>
                    <div class="chart-container">
                        <canvas id="holdTimeEuroChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Table sorting functionality
        document.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const table = th.closest('table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const colIndex = Array.from(th.parentNode.children).indexOf(th);
                const sortType = th.dataset.sort;

                // Toggle sort direction
                const isAsc = th.classList.contains('asc');

                // Remove sort classes from all headers in this table
                table.querySelectorAll('th.sortable').forEach(header => {
                    header.classList.remove('asc', 'desc');
                });

                // Set new sort direction
                th.classList.add(isAsc ? 'desc' : 'asc');
                const direction = isAsc ? -1 : 1;

                rows.sort((a, b) => {
                    let aVal = a.cells[colIndex].textContent.trim();
                    let bVal = b.cells[colIndex].textContent.trim();

                    if (sortType === 'number') {
                        // Parse numbers (handle German format and currency)
                        aVal = parseFloat(aVal.replace(/[^\\d,.-]/g, '').replace('.', '').replace(',', '.')) || 0;
                        bVal = parseFloat(bVal.replace(/[^\\d,.-]/g, '').replace('.', '').replace(',', '.')) || 0;
                        return (aVal - bVal) * direction;
                    } else if (sortType === 'date') {
                        // Parse German date format DD.MM.YYYY
                        const aParts = aVal.split('.');
                        const bParts = bVal.split('.');
                        aVal = new Date(aParts[2], aParts[1] - 1, aParts[0]);
                        bVal = new Date(bParts[2], bParts[1] - 1, bParts[0]);
                        return (aVal - bVal) * direction;
                    } else {
                        return aVal.localeCompare(bVal, 'de') * direction;
                    }
                });

                rows.forEach(row => tbody.appendChild(row));
            });
        });
"""

    # Generate P&L over time data - calculate from individual sales using average cost basis
    pnl_events = []

    # Build cost basis per ISIN and calculate P&L for each sale
    cost_basis_by_isin = {}  # ISIN -> {"total_cost": float, "total_stueck": float}

    # Collect all trade transactions and sort by date
    all_trade_transactions = sorted(trades, key=lambda t: t.datum)

    for t in all_trade_transactions:
        if not t.isin:
            continue

        if t.isin not in cost_basis_by_isin:
            cost_basis_by_isin[t.isin] = {"total_cost": 0.0, "total_stueck": 0.0, "name": t.name}

        basis = cost_basis_by_isin[t.isin]

        if t.is_kauf:
            # Add to cost basis (betrag is negative for purchases)
            basis["total_cost"] += abs(t.betrag)
            basis["total_stueck"] += t.stueck
        elif t.is_verkauf and t.stueck > 0:
            # Calculate realized P&L for this sale
            if basis["total_stueck"] > 0:
                avg_cost_per_unit = basis["total_cost"] / basis["total_stueck"]
                cost_of_sold = avg_cost_per_unit * t.stueck
                realized_pnl = t.betrag - cost_of_sold  # betrag is positive for sales

                pnl_events.append({
                    "date": t.datum,
                    "pnl": realized_pnl,
                    "type": "Trade",
                    "name": basis["name"][:30]
                })

                # Reduce cost basis
                basis["total_cost"] -= cost_of_sold
                basis["total_stueck"] -= t.stueck

    # Add dividends
    for t in dividenden:
        pnl_events.append({
            "date": t.datum,
            "pnl": t.betrag,
            "type": "Dividende",
            "name": t.isin or "Dividende"
        })

    # Add steuerausgleich
    for t in steuerausgleich:
        pnl_events.append({
            "date": t.datum,
            "pnl": t.betrag,
            "type": "Steuerausgleich",
            "name": "Steuerausgleich"
        })

    # Sort by date and calculate cumulative P&L
    pnl_events.sort(key=lambda x: x["date"])
    cumulative_pnl = 0
    pnl_timeline = []
    for event in pnl_events:
        cumulative_pnl += event["pnl"]
        pnl_timeline.append({
            "date": event["date"].strftime("%Y-%m-%d"),
            "cumulative": round(cumulative_pnl, 2),
            "change": round(event["pnl"], 2),
            "type": event["type"],
            "name": event["name"]
        })
        # Aggregate P&L by month
        month_key = event["date"].strftime("%Y-%m")
        pnl_by_month[month_key] += event["pnl"]

    # Generate scatter plot data for closed positions
    scatter_data_pct = []
    scatter_data_euro = []
    for pos in closed_positions:
        hold_days = pos.get("hold_days", 0)
        rendite_pct = pos.get("rendite_pct", 0)
        pnl_euro = pos.get("pnl", 0)
        name = pos.get("name", "")[:25]
        scatter_data_pct.append({
            "x": hold_days,
            "y": round(rendite_pct, 2),
            "name": name,
            "pnl": round(pnl_euro, 2)
        })
        scatter_data_euro.append({
            "x": hold_days,
            "y": round(pnl_euro, 2),
            "name": name,
            "pct": round(rendite_pct, 2)
        })

    # Generate volume chart data
    sorted_months = sorted(volume_by_month.keys())
    volume_month_data = {
        "labels": sorted_months,
        "kauf": [round(volume_by_month[m]["kauf"], 2) for m in sorted_months],
        "verkauf": [round(volume_by_month[m]["verkauf"], 2) for m in sorted_months],
        "count": [volume_by_month[m]["count"] for m in sorted_months],
        "pnl": [round(pnl_by_month[m], 2) for m in sorted_months]
    }

    volume_weekday_data = {
        "labels": weekday_names,
        "kauf": [round(volume_by_weekday[i]["kauf"], 2) for i in range(7)],
        "verkauf": [round(volume_by_weekday[i]["verkauf"], 2) for i in range(7)],
        "count": [volume_by_weekday[i]["count"] for i in range(7)]
    }

    html += f"""
        // Volume Charts
        const volumeMonthData = {json.dumps(volume_month_data)};
        const volumeWeekdayData = {json.dumps(volume_weekday_data)};

        // Plugin to draw P&L under x-axis labels
        const pnlLabelPlugin = {{
            id: 'pnlLabels',
            afterDraw: function(chart) {{
                const ctx = chart.ctx;
                const xAxis = chart.scales.x;
                const yAxis = chart.scales.y;

                ctx.save();
                ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif';
                ctx.textAlign = 'center';

                volumeMonthData.pnl.forEach((pnl, i) => {{
                    const x = xAxis.getPixelForValue(i);
                    const y = yAxis.bottom + 32;

                    ctx.fillStyle = pnl >= 0 ? '#10b981' : '#ef4444';
                    const sign = pnl >= 0 ? '+' : '';
                    ctx.fillText(sign + pnl.toLocaleString('de-DE') + '€', x, y);
                }});

                ctx.restore();
            }}
        }};

        // Volume per Month Chart
        const volumeMonthCtx = document.getElementById('volumeMonthChart').getContext('2d');
        const volumeMonthChart = new Chart(volumeMonthCtx, {{
            type: 'bar',
            plugins: [pnlLabelPlugin],
            data: {{
                labels: volumeMonthData.labels.map(m => {{
                    const [year, month] = m.split('-');
                    const date = new Date(year, month - 1);
                    return date.toLocaleDateString('de-DE', {{ month: 'short', year: '2-digit' }});
                }}),
                datasets: [
                    {{
                        label: 'Käufe',
                        data: volumeMonthData.kauf,
                        backgroundColor: 'rgba(239, 68, 68, 0.7)',
                        borderColor: '#ef4444',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Verkäufe',
                        data: volumeMonthData.verkauf,
                        backgroundColor: 'rgba(16, 185, 129, 0.7)',
                        borderColor: '#10b981',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                layout: {{
                    padding: {{ bottom: 20 }}
                }},
                plugins: {{
                    legend: {{
                        display: true,
                        labels: {{ color: '#888' }}
                    }},
                    tooltip: {{
                        callbacks: {{
                            afterBody: function(context) {{
                                const idx = context[0].dataIndex;
                                return ['Trades: ' + volumeMonthData.count[idx], 'P&L: ' + (volumeMonthData.pnl[idx] >= 0 ? '+' : '') + volumeMonthData.pnl[idx].toLocaleString('de-DE') + ' €'];
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        stacked: false,
                        ticks: {{ color: '#666' }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }},
                    y: {{
                        stacked: false,
                        ticks: {{
                            color: '#666',
                            callback: function(value) {{ return value.toLocaleString('de-DE') + ' €'; }}
                        }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }}
                }}
            }}
        }});

        // Volume per Weekday Chart
        const volumeWeekdayCtx = document.getElementById('volumeWeekdayChart').getContext('2d');
        const volumeWeekdayChart = new Chart(volumeWeekdayCtx, {{
            type: 'bar',
            data: {{
                labels: volumeWeekdayData.labels,
                datasets: [
                    {{
                        label: 'Käufe',
                        data: volumeWeekdayData.kauf,
                        backgroundColor: 'rgba(239, 68, 68, 0.7)',
                        borderColor: '#ef4444',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Verkäufe',
                        data: volumeWeekdayData.verkauf,
                        backgroundColor: 'rgba(16, 185, 129, 0.7)',
                        borderColor: '#10b981',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        labels: {{ color: '#888' }}
                    }},
                    tooltip: {{
                        callbacks: {{
                            afterBody: function(context) {{
                                const idx = context[0].dataIndex;
                                return 'Trades: ' + volumeWeekdayData.count[idx];
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        stacked: false,
                        ticks: {{ color: '#666' }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }},
                    y: {{
                        stacked: false,
                        ticks: {{
                            color: '#666',
                            callback: function(value) {{ return value.toLocaleString('de-DE') + ' €'; }}
                        }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }}
                }}
            }}
        }});

        // Log scale toggle
        document.getElementById('logScaleToggle').addEventListener('change', function() {{
            const isLog = this.checked;
            const scaleType = isLog ? 'logarithmic' : 'linear';

            volumeMonthChart.options.scales.y.type = scaleType;
            volumeWeekdayChart.options.scales.y.type = scaleType;

            if (isLog) {{
                volumeMonthChart.options.scales.y.min = 1;
                volumeWeekdayChart.options.scales.y.min = 1;
                // Log-friendly ticks
                volumeMonthChart.options.scales.y.ticks = {{
                    color: '#666',
                    callback: function(value) {{
                        if (value === 1 || value === 10 || value === 100 || value === 1000 || value === 10000 || value === 100000) {{
                            return value.toLocaleString('de-DE') + ' €';
                        }}
                        return '';
                    }}
                }};
                volumeWeekdayChart.options.scales.y.ticks = {{
                    color: '#666',
                    callback: function(value) {{
                        if (value === 1 || value === 10 || value === 100 || value === 1000 || value === 10000 || value === 100000) {{
                            return value.toLocaleString('de-DE') + ' €';
                        }}
                        return '';
                    }}
                }};
            }} else {{
                delete volumeMonthChart.options.scales.y.min;
                delete volumeWeekdayChart.options.scales.y.min;
                // Linear ticks
                volumeMonthChart.options.scales.y.ticks = {{
                    color: '#666',
                    callback: function(value) {{ return value.toLocaleString('de-DE') + ' €'; }}
                }};
                volumeWeekdayChart.options.scales.y.ticks = {{
                    color: '#666',
                    callback: function(value) {{ return value.toLocaleString('de-DE') + ' €'; }}
                }};
            }}

            volumeMonthChart.update();
            volumeWeekdayChart.update();
        }});

        // P&L Over Time Chart
        const pnlTimeline = {json.dumps(pnl_timeline)};

        const pnlCtx = document.getElementById('pnlOverTimeChart').getContext('2d');
        new Chart(pnlCtx, {{
            type: 'line',
            data: {{
                labels: pnlTimeline.map(d => d.date),
                datasets: [{{
                    label: 'Kumulierte P&L',
                    data: pnlTimeline.map(d => d.cumulative),
                    borderColor: '#00d4ff',
                    backgroundColor: 'rgba(0, 212, 255, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 6,
                    pointHoverRadius: 10,
                    pointBackgroundColor: pnlTimeline.map(d => d.change >= 0 ? '#10b981' : '#ef4444'),
                    pointBorderColor: pnlTimeline.map(d => d.change >= 0 ? '#10b981' : '#ef4444'),
                    pointBorderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    intersect: false,
                    mode: 'index'
                }},
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            title: function(context) {{
                                const idx = context[0].dataIndex;
                                const d = pnlTimeline[idx];
                                const date = new Date(d.date);
                                return date.toLocaleDateString('de-DE');
                            }},
                            label: function(context) {{
                                const idx = context.dataIndex;
                                const d = pnlTimeline[idx];
                                return [
                                    d.type + ': ' + d.name,
                                    'Änderung: ' + (d.change >= 0 ? '+' : '') + d.change.toLocaleString('de-DE') + ' €',
                                    'Kumuliert: ' + (d.cumulative >= 0 ? '+' : '') + d.cumulative.toLocaleString('de-DE') + ' €'
                                ];
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        type: 'category',
                        title: {{ display: true, text: 'Datum', color: '#888' }},
                        ticks: {{
                            color: '#666',
                            maxRotation: 45,
                            minRotation: 45,
                            callback: function(value, index) {{
                                const date = new Date(pnlTimeline[index].date);
                                return date.toLocaleDateString('de-DE', {{ month: 'short', year: '2-digit' }});
                            }}
                        }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }},
                    y: {{
                        title: {{ display: true, text: 'Kumulierte P&L (€)', color: '#888' }},
                        ticks: {{
                            color: '#666',
                            callback: function(value) {{ return value.toLocaleString('de-DE') + ' €'; }}
                        }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }}
                }}
            }}
        }});

        // Chart.js configuration - Scatter plots
        const scatterDataPct = {json.dumps(scatter_data_pct)};
        const scatterDataEuro = {json.dumps(scatter_data_euro)};

        // Hold time vs Rendite %
        const pctCtx = document.getElementById('holdTimePctChart').getContext('2d');
        new Chart(pctCtx, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    label: 'Geschlossene Positionen',
                    data: scatterDataPct,
                    backgroundColor: scatterDataPct.map(d => d.y >= 0 ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)'),
                    borderColor: scatterDataPct.map(d => d.y >= 0 ? '#10b981' : '#ef4444'),
                    borderWidth: 2,
                    pointRadius: 8,
                    pointHoverRadius: 12
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const d = context.raw;
                                return [d.name, 'Haltedauer: ' + d.x + ' Tage', 'Rendite: ' + d.y.toLocaleString('de-DE') + ' %', 'P&L: ' + d.pnl.toLocaleString('de-DE') + ' €'];
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Haltedauer (Tage)', color: '#888' }},
                        ticks: {{ color: '#666' }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }},
                    y: {{
                        title: {{ display: true, text: 'Rendite (%)', color: '#888' }},
                        ticks: {{
                            color: '#666',
                            callback: function(value) {{ return value.toLocaleString('de-DE') + ' %'; }}
                        }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }}
                }}
            }}
        }});

        // Hold time vs Rendite €
        const euroCtx = document.getElementById('holdTimeEuroChart').getContext('2d');
        new Chart(euroCtx, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    label: 'Geschlossene Positionen',
                    data: scatterDataEuro,
                    backgroundColor: scatterDataEuro.map(d => d.y >= 0 ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)'),
                    borderColor: scatterDataEuro.map(d => d.y >= 0 ? '#10b981' : '#ef4444'),
                    borderWidth: 2,
                    pointRadius: 8,
                    pointHoverRadius: 12
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const d = context.raw;
                                return [d.name, 'Haltedauer: ' + d.x + ' Tage', 'P&L: ' + d.y.toLocaleString('de-DE') + ' €', 'Rendite: ' + d.pct.toLocaleString('de-DE') + ' %'];
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Haltedauer (Tage)', color: '#888' }},
                        ticks: {{ color: '#666' }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }},
                    y: {{
                        title: {{ display: true, text: 'Rendite (€)', color: '#888' }},
                        ticks: {{
                            color: '#666',
                            callback: function(value) {{ return value.toLocaleString('de-DE') + ' €'; }}
                        }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML report generated: {output_path}")


def main():
    csv_file = Path(__file__).parent / "ZERO-kontoumsaetze-28.01.2026.csv"
    html_file = Path(__file__).parent / "trades_overview.html"

    print(f"Reading {csv_file}...")
    transactions = read_csv(str(csv_file))

    print(f"Total transactions: {len(transactions)}")

    # Trade summary - include Orders, Sparpläne, Bruchstücke, and WP-Abrechnungen
    trade_types = ["Order", "Sparplan", "Bruchstücke", "WP-Abrechnung"]
    trades = [t for t in transactions if t.typ in trade_types]
    kaufe = [t for t in trades if t.is_kauf]
    verkaeufe = [t for t in trades if t.is_verkauf]

    print(f"Trades: {len(trades)} ({len(kaufe)} Käufe, {len(verkaeufe)} Verkäufe)")

    # Calculate open/closed for console output
    trades_by_isin = {}
    for t in trades:
        if not t.isin:
            continue
        if t.isin not in trades_by_isin:
            trades_by_isin[t.isin] = {"kaufe": [], "verkaeufe": []}
        if t.is_kauf:
            trades_by_isin[t.isin]["kaufe"].append(t)
        else:
            trades_by_isin[t.isin]["verkaeufe"].append(t)

    total_realized = 0.0
    total_invested_open = 0.0
    open_count = 0
    closed_count = 0

    for isin, data in trades_by_isin.items():
        kauf_sum = sum(t.betrag for t in data["kaufe"])
        verkauf_sum = sum(t.betrag for t in data["verkaeufe"])
        kauf_stueck = sum(t.stueck for t in data["kaufe"])
        verkauf_stueck = sum(t.stueck for t in data["verkaeufe"])
        open_stueck = kauf_stueck - verkauf_stueck

        if abs(open_stueck) < 0.001:  # Closed
            total_realized += verkauf_sum + kauf_sum
            closed_count += 1
        else:  # Open
            open_count += 1
            if kauf_stueck > 0:
                avg_price = abs(kauf_sum) / kauf_stueck
                total_invested_open += open_stueck * avg_price
                if verkauf_stueck > 0:
                    cost_of_sold = (verkauf_stueck / kauf_stueck) * abs(kauf_sum)
                    total_realized += verkauf_sum - cost_of_sold

    # Add Steuerausgleich and Dividenden
    steuerausgleich = sum(t.betrag for t in transactions if t.typ == "Steuerausgleich")
    dividenden = sum(t.betrag for t in transactions if t.typ == "Dividende")
    total_realized += steuerausgleich + dividenden

    print(f"\nOffene Positionen: {open_count}")
    print(f"Geschlossene Positionen: {closed_count}")
    print(f"Steuerausgleich: {steuerausgleich:,.2f} EUR")
    print(f"Dividenden: {dividenden:,.2f} EUR")
    print(f"Realisierte P&L (inkl. Steuer+Div): {total_realized:,.2f} EUR")
    print(f"Noch investiert (offene Pos.): {total_invested_open:,.2f} EUR")

    generate_html(transactions, str(html_file))


if __name__ == "__main__":
    main()
