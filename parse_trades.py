import csv
import re
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

    # Calculate totals
    total_realized_pnl = sum(p["pnl"] for p in closed_positions)
    total_realized_pnl += sum(p.get("realized_pnl", 0) for p in open_positions)
    total_realized_pnl += total_steuerausgleich + total_dividenden
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
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
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
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Trade Übersicht</h1>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Einzahlungen</div>
                <div class="stat-value positive">{total_einzahlung:,.2f} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Auszahlungen</div>
                <div class="stat-value negative">{total_auszahlung:,.2f} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Realisierte P&L</div>
                <div class="stat-value {'positive' if total_realized_pnl >= 0 else 'negative'}">{'+' if total_realized_pnl >= 0 else ''}{total_realized_pnl:,.2f} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Investiert (offen)</div>
                <div class="stat-value neutral">{total_invested_open:,.2f} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Steuerausgleich</div>
                <div class="stat-value positive">+{total_steuerausgleich:,.2f} €</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Dividenden</div>
                <div class="stat-value positive">+{total_dividenden:,.2f} €</div>
            </div>
        </div>

        <div class="section">
            <h2>📂 Offene Positionen (noch gehalten)</h2>
            <table>
                <thead>
                    <tr>
                        <th>ISIN</th>
                        <th>Name</th>
                        <th class="text-right">Stück</th>
                        <th class="text-right">Ø Kaufpreis</th>
                        <th class="text-right">Investiert</th>
                        <th class="text-right">Realisiert</th>
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
                        <td class="text-right mono">{item["open_stueck"]:,.2f}</td>
                        <td class="text-right mono">{item.get("avg_kauf_preis", 0):,.2f} €</td>
                        <td class="text-right mono">{item.get("invested", 0):,.2f} €</td>
                        <td class="text-right mono {realized_class}">{realized_sign}{realized:,.2f} €</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>✅ Geschlossene Positionen</h2>
            <table>
                <thead>
                    <tr>
                        <th>ISIN</th>
                        <th>Name</th>
                        <th class="text-right">Käufe</th>
                        <th class="text-right">Verkäufe</th>
                        <th class="text-right">Investiert</th>
                        <th class="text-right">Erlös</th>
                        <th class="text-right">P&L</th>
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
                        <td class="text-right mono negative">{item["kauf_sum"]:,.2f} €</td>
                        <td class="text-right mono positive">+{item["verkauf_sum"]:,.2f} €</td>
                        <td class="text-right mono {pnl_class}">{pnl_sign}{item["pnl"]:,.2f} €</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>📋 Alle Trades</h2>
            <div class="trades-table">
                <table>
                    <thead>
                        <tr>
                            <th>Datum</th>
                            <th>Typ</th>
                            <th>ISIN</th>
                            <th>Name</th>
                            <th class="text-right">Stück</th>
                            <th class="text-right">Betrag</th>
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
                            <td class="text-right mono">{t.stueck:,.2f}</td>
                            <td class="text-right mono {betrag_class}">{betrag_sign}{t.betrag:,.2f} €</td>
                        </tr>
"""

    html += """                    </tbody>
                </table>
            </div>
        </div>
    </div>
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
