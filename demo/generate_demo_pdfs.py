"""
Generate simple placeholder PDFs for the demo deployment.

Uses fpdf2 to create minimal but viewable PDF files that look
like Swiss bank statements and invoices. All content is
completely fictitious.

Install: pip install fpdf2
Usage:   python demo/generate_demo_pdfs.py [output_dir]
"""

import sys
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("fpdf2 is required: pip install fpdf2")
    sys.exit(1)


def _create_pdf(title: str, lines: list[str], path: Path):
    """Create a simple single-page PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(4)
    for line in lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def generate_all(base_dir: Path):
    """Generate all demo PDFs under the given base directory."""

    # --- Pending invoices ---
    pendent = base_dir / "01-Rechnungen-Pendent"

    _create_pdf(
        "Alpenenergie Strom AG",
        [
            "Stromrechnung Q1 2026",
            "",
            "Rechnungsbetrag inkl. MWST in CHF 245.80",
            "Zahlbar bis: 21.04.2026",
            "",
            "IBAN: CH93 0076 2011 6238 5295 7",
            "Waehrung Betrag",
            "CHF 245.80",
            "",
            "Vor der Einzahlung abzutrennen",
        ],
        pendent / "2026-04-rechnung-alpenenergie.pdf",
    )

    _create_pdf(
        "Panorama Versicherung AG",
        [
            "Krankenversicherung - Praemienrechnung April 2026",
            "",
            "Monatliche Praemie: CHF 380.00",
            "Zahlbar bis: 14.04.2026",
            "",
            "IBAN: CH43 0830 7000 2895 3732 0",
            "Waehrung Betrag",
            "CHF 380.00",
        ],
        pendent / "2026-04-rechnung-panorama.pdf",
    )

    _create_pdf(
        "Steueramt Fantasieberg",
        [
            "Gemeindesteuer 2025 - Definitive Veranlagung",
            "",
            "Steuerbetrag: CHF 1'870.50",
            "Zahlbar bis: 04.05.2026",
            "",
            "Konto: Einwohnergemeinde Fantasieberg",
            "IBAN: CH20 8914 4416 5445 6584 4",
            "Waehrung Betrag",
            "CHF 1'870.50",
        ],
        pendent / "2026-04-rechnung-fantasie-steueramt.pdf",
    )

    _create_pdf(
        "Gaswerk Mustertal AG",
        [
            "Gasrechnung Heizperiode Oktober 2025 - Maerz 2026",
            "",
            "Gesamtbetrag CHF 520.00",
            "Zahlbar bis: 06.04.2026",
            "",
            "IBAN: CH55 5550 0000 0555 5555 5",
            "Waehrung Betrag",
            "CHF 520.00",
        ],
        pendent / "2026-04-rechnung-gaswerk.pdf",
    )

    _create_pdf(
        "Zahnklinik Alpenpanorama",
        [
            "Zahnkontrolle und Dentalhygiene",
            "Behandlungsdatum: 25.03.2026",
            "",
            "Total CHF 185.00",
            "Zahlbar bis: 27.04.2026",
            "",
            "Waehrung Betrag",
            "CHF 185.00",
        ],
        pendent / "2026-04-rechnung-zahnarzt.pdf",
    )

    # --- Paid invoices ---
    bezahlt = base_dir / "02-Rechnungen-Bezahlt" / "2026"

    _create_pdf(
        "Immobilien Fantasiegasse GmbH",
        [
            "Miete Maerz 2026 - Fantasiegasse 12, 3000 Fantasieberg",
            "",
            "Nettomiete: CHF 1'250.00",
            "Nebenkosten: CHF 200.00",
            "Total: CHF 1'450.00",
            "",
            "Zahlbar bis: 01.03.2026",
            "Bezahlt am: 28.02.2026",
        ],
        bezahlt / "2026-03-rechnung-miete.pdf",
    )

    _create_pdf(
        "Mondschein Telecom AG",
        [
            "Mobilabo Maerz 2026",
            "",
            "Abo Swiss Plus: CHF 49.00",
            "Zahlbar bis: 15.03.2026",
            "Bezahlt am: 10.03.2026",
        ],
        bezahlt / "2026-03-rechnung-telecom.pdf",
    )

    _create_pdf(
        "Alpennet Internet AG",
        [
            "Internetanschluss Februar 2026",
            "",
            "Glasfaser 1 Gbit/s: CHF 39.90",
            "Zahlbar bis: 20.02.2026",
            "Bezahlt am: 18.02.2026",
        ],
        bezahlt / "2026-02-rechnung-internet.pdf",
    )

    _create_pdf(
        "Schutzschild Versicherung AG",
        [
            "Privathaftpflicht - Jahrespraemie 2026",
            "",
            "Praemie: CHF 342.00",
            "Zahlbar bis: 01.02.2026",
            "Bezahlt am: 29.01.2026",
        ],
        bezahlt / "2026-02-rechnung-haftpflicht.pdf",
    )

    _create_pdf(
        "Fitnesspark Alpenblick",
        [
            "Jahresabonnement 2026",
            "",
            "Fitness & Wellness: CHF 828.00",
            "Zahlbar bis: 15.01.2026",
            "Bezahlt am: 12.01.2026",
        ],
        bezahlt / "2026-01-rechnung-fitness.pdf",
    )

    # --- Bank statements ---
    bewegungen = base_dir / "03-Bewegungen"

    _create_pdf(
        "Fantasie Bank AG - Kontoauszug",
        [
            "Kontoauszug per 31.03.2026",
            "Konto: Privatkonto CHF",
            "IBAN: CH93 0076 2011 6238 5295 7",
            "",
            "Datum       Beschreibung                    Belastung    Gutschrift    Saldo",
            "01.03.26    Gehalt Musterwerk AG                         5'800.00      12'500.00",
            "01.03.26    Miete Fantasiegasse 12          1'450.00                   11'050.00",
            "03.03.26    Einkauf Alpenhof Markt AG       87.50                      10'962.50",
            "05.03.26    Panorama Versicherung           380.00                     10'582.50",
            "10.03.26    Restaurant Sonnenberg           45.80                      10'536.70",
            "15.03.26    E-Banking-Auftrag               285.00                     10'251.70",
            "",
            "                                                         DEMO - Fictitious Data",
        ],
        bewegungen / "BEKB" / "CH9300762011623852957_20260331_Kontoauszug_demo.pdf",
    )

    _create_pdf(
        "Beispiel Sparkonto - Kontoauszug",
        [
            "Kontoauszug per 31.03.2026",
            "Konto: Sparkonto CHF",
            "IBAN: CH43 0830 7000 2895 3732 0",
            "",
            "28.03.26    Zinsgutschrift                               15.30         8'515.30",
            "",
            "                                                         DEMO - Fictitious Data",
        ],
        bewegungen / "BEKB" / "CH4308307000289537320_20260331_Kontoauszug_demo.pdf",
    )

    _create_pdf(
        "Revolut - Account Statement",
        [
            "Account Statement",
            "01 Nov 2025 - 01 Apr 2026",
            "IBAN: CH20 8914 4416 5445 6584 4",
            "",
            "Date         Description                 Amount CHF    Balance CHF",
            "15 Mar 2026  Einkauf Bergkaese Laden     -45.30        1'254.70",
            "12 Mar 2026  Pizzeria Bellavista          -32.00        1'299.70",
            "01 Mar 2026  Top Up                       500.00        1'331.70",
            "",
            "                                          DEMO - Fictitious Data",
        ],
        bewegungen / "Revolut" / "account-statement_2026-04-01_demo.pdf",
    )

    print(f"Generated demo PDFs in {base_dir}")


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo/example")
    generate_all(output)
