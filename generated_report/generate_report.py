from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUT = Path(r"C:\Users\zinem\OneDrive\Desktop\HR_django\generated_report")
OUT.mkdir(exist_ok=True)

cover_pdf = OUT / "ancienne_page_de_garde.pdf"
front_pdf = OUT / "rapport_pfa_hr_django_preliminaires.pdf"
main_pdf = OUT / "rapport_pfa_hr_django_corps.pdf"
final_pdf = OUT / "rapport_pfa_hr_django_final.pdf"
md_path = OUT / "rapport_pfa_hr_django_source.md"

FONT_DIR = Path(r"C:\Windows\Fonts")
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", str(FONT_DIR / "ariali.ttf")))

PAGE_W, PAGE_H = A4
LEFT = RIGHT = 2.1 * cm
TOP = 2.0 * cm
BOTTOM = 2.0 * cm
TEXT_W = PAGE_W - LEFT - RIGHT

styles = {
    "Title": ParagraphStyle(
        "Title",
        fontName="Arial-Bold",
        fontSize=18,
        leading=23,
        alignment=TA_CENTER,
        spaceAfter=18,
        textColor=colors.HexColor("#111827"),
    ),
    "H1": ParagraphStyle(
        "H1",
        fontName="Arial-Bold",
        fontSize=16,
        leading=20,
        spaceBefore=8,
        spaceAfter=10,
        textColor=colors.HexColor("#111827"),
    ),
    "H2": ParagraphStyle(
        "H2",
        fontName="Arial-Bold",
        fontSize=12.5,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#1f2937"),
    ),
    "H3": ParagraphStyle(
        "H3",
        fontName="Arial-Bold",
        fontSize=11.2,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.HexColor("#374151"),
    ),
    "Body": ParagraphStyle(
        "Body",
        fontName="Arial",
        fontSize=10.2,
        leading=14.6,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ),
    "BodyLeft": ParagraphStyle(
        "BodyLeft",
        fontName="Arial",
        fontSize=10.2,
        leading=14.4,
        alignment=TA_LEFT,
        spaceAfter=6,
    ),
    "Small": ParagraphStyle(
        "Small", fontName="Arial", fontSize=8.8, leading=11.5, alignment=TA_LEFT
    ),
    "Caption": ParagraphStyle(
        "Caption",
        fontName="Arial-Italic",
        fontSize=9,
        leading=11.5,
        alignment=TA_CENTER,
        spaceBefore=4,
        spaceAfter=8,
        textColor=colors.HexColor("#374151"),
    ),
    "Bullet": ParagraphStyle(
        "Bullet",
        fontName="Arial",
        fontSize=10.0,
        leading=13.8,
        leftIndent=12,
        firstLineIndent=0,
        spaceAfter=3,
    ),
    "TOC": ParagraphStyle(
        "TOC", fontName="Arial", fontSize=10.0, leading=13.5, spaceAfter=3
    ),
    "TableHead": ParagraphStyle(
        "TableHead",
        fontName="Arial-Bold",
        fontSize=8.8,
        leading=11,
        textColor=colors.white,
        alignment=TA_CENTER,
    ),
    "TableCell": ParagraphStyle(
        "TableCell",
        fontName="Arial",
        fontSize=8.4,
        leading=10.8,
        alignment=TA_LEFT,
    ),
    "DiagramBox": ParagraphStyle(
        "DiagramBox",
        fontName="Arial-Bold",
        fontSize=8.2,
        leading=10.2,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111827"),
    ),
}

md = []


def para(text, style="Body"):
    return Paragraph(escape(text), styles[style])


def h1(text):
    md.append(f"\n# {text}\n")
    return Paragraph(escape(text), styles["H1"])


def h2(text):
    md.append(f"\n## {text}\n")
    return Paragraph(escape(text), styles["H2"])


def add_par(story, text, style="Body"):
    story.append(para(text, style))
    md.append(text + "\n")


def add_bullets(story, items):
    flow = ListFlowable(
        [
            ListItem(para(item, "Bullet"), bulletColor=colors.HexColor("#111827"))
            for item in items
        ],
        bulletType="bullet",
        start="circle",
    )
    story.append(flow)
    story.append(Spacer(1, 4))
    for item in items:
        md.append(f"- {item}\n")


def make_table(data, col_widths=None, header=True, font_size=8.4):
    table_data = []
    for r, row in enumerate(data):
        trow = []
        for cell in row:
            if r == 0 and header:
                trow.append(Paragraph(escape(str(cell)), styles["TableHead"]))
            else:
                style = ParagraphStyle(
                    "TmpCell",
                    parent=styles["TableCell"],
                    fontSize=font_size,
                    leading=font_size + 2.4,
                )
                trow.append(Paragraph(escape(str(cell)), style))
        table_data.append(trow)
    table = Table(table_data, colWidths=col_widths, repeatRows=1 if header else 0)
    table_style = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        table_style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    for i in range(1 if header else 0, len(data)):
        if i % 2 == 0:
            table_style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f9fafb")))
    table.setStyle(TableStyle(table_style))
    return table


def add_table(story, number, title, data, col_widths=None, font_size=8.4):
    story.append(Spacer(1, 4))
    story.append(make_table(data, col_widths=col_widths, font_size=font_size))
    caption = f"Tableau {number} : {title}" if number else title
    story.append(Paragraph(escape(caption), styles["Caption"]))
    md.append(f"\n**{caption}**\n\n")
    for row in data:
        md.append("| " + " | ".join(str(c) for c in row) + " |\n")
    md.append("\n")


def add_figure(story, number, title, rows, col_widths=None):
    data = [[Paragraph(escape(str(cell)), styles["DiagramBox"]) for cell in row] for row in rows]
    table = Table(data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    caption = f"Figure {number} : {title}"
    story.append(KeepTogether([Spacer(1, 6), table, Paragraph(escape(caption), styles["Caption"])]))
    md.append(f"\n**{caption}**\n\n")
    for row in rows:
        md.append(" | ".join(str(c) for c in row) + "\n")
    md.append("\n")


def roman(num):
    vals = [
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    ]
    out = ""
    for value, symbol in vals:
        while num >= value:
            out += symbol
            num -= value
    return out


def front_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(LEFT, 1.1 * cm, "Plateforme RH Django")
    canvas.drawRightString(PAGE_W - RIGHT, 1.1 * cm, roman(doc.page))
    canvas.restoreState()


def main_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(LEFT, 1.1 * cm, "Plateforme RH Django")
    canvas.drawRightString(PAGE_W - RIGHT, 1.1 * cm, str(doc.page))
    canvas.restoreState()


FRONT_MATTER = {
    "Remerciements": [
        "Nous tenons à exprimer notre sincère gratitude à Dr. Houda Orchi pour son encadrement, ses conseils méthodologiques et son accompagnement tout au long de la réalisation de ce Projet de Fin d'Année. Ses remarques nous ont aidés à structurer notre démarche, à clarifier les besoins du système et à améliorer la qualité globale de la solution présentée.",
        "Nous remercions également l'ensemble des personnes qui nous ont soutenus, directement ou indirectement, durant les phases d'analyse, de conception, de développement, de test et de rédaction. Leur aide a contribué à transformer une application RH existante en une plateforme plus cohérente, plus fiable et plus adaptée aux usages professionnels.",
        "Enfin, nous adressons nos remerciements à notre établissement et à l'équipe pédagogique pour l'environnement de travail, les connaissances techniques et les orientations qui ont rendu possible la conduite de ce projet.",
    ],
    "Résumé": [
        "Ce rapport présente la conception et la réalisation d'une plateforme web de gestion des ressources humaines développée avec Django. L'application centralise les principaux processus RH : authentification, gestion des employés, organisation interne, congés, demandes administratives, documents, notifications, audit, pointage, planning, tâches d'équipe, formations, messagerie RH, actualités, boutique interne, réclamations, points et analyses salariales.",
        "L'amélioration majeure porte sur le module Planning. Celui-ci devient un système opérationnel capable de gérer des shifts normaux, des plans permanents, des récurrences, des filtres dynamiques, des vues journalières, hebdomadaires, sur deux semaines et mensuelles, des statistiques compactes, une création groupée et une API JSON. Le Planning est relié au module Présence / Pointage afin que les retards, sorties anticipées, heures manquantes et heures supplémentaires soient calculés à partir du shift réellement planifié.",
        "Le projet intègre également un assistant intelligent basé sur Gemini. L'assistant général utilise une approche RAG sécurisée, tandis que l'assistant Planning peut répondre à des questions sur les conflits, les employés sans planning et les heures planifiées. Les actions sensibles restent validées côté backend et limitées aux rôles autorisés.",
    ],
    "Mots-clés": [
        "Django, gestion des ressources humaines, planning, pointage, plan permanent, RAG, Gemini, sécurité, rôles, API, tests automatisés."
    ],
    "Abstract": [
        "This report presents the design and implementation of a Django-based human resources management platform. The application centralizes core HR processes such as authentication, employee records, organization management, leave requests, administrative requests, documents, notifications, audit logs, attendance, planning, team tasks, training, HR messaging, news, internal shop, claims, points and payroll analytics.",
        "The main improvement concerns the Planning module. It now supports normal shifts, permanent plans, recurrence rules, dynamic filters, daily, weekly, biweekly and monthly views, compact statistics, bulk creation and JSON APIs. Planning is connected to Presence / Pointage so that late arrivals, early departures, missing hours and overtime are calculated from the employee's planned shift.",
        "The project also includes a Gemini-powered assistant. The global assistant uses a secure RAG approach, while the Planning assistant can answer questions about conflicts, employees without planning and planned hours. Sensitive actions remain validated by the backend and restricted to authorized roles.",
    ],
    "Keywords": [
        "Django, human resources management, planning, attendance, permanent plan, RAG, Gemini, security, roles, API, automated tests."
    ],
}

ABBREVIATIONS = [
    ("API", "Application Programming Interface : interface permettant à deux composants logiciels de communiquer."),
    ("CRUD", "Create, Read, Update, Delete : opérations de base sur les données."),
    ("CSRF", "Cross-Site Request Forgery : attaque empêchée par les protections Django sur les formulaires."),
    ("KPI", "Key Performance Indicator : indicateur de performance utilisé dans les tableaux de bord."),
    ("ORM", "Object-Relational Mapping : mécanisme Django reliant les objets Python aux tables SQL."),
    ("RAG", "Retrieval-Augmented Generation : génération de réponse enrichie par un contexte récupéré."),
    ("RH", "Ressources humaines."),
    ("UI", "User Interface : interface utilisateur."),
    ("UX", "User Experience : expérience utilisateur."),
    ("URL", "Uniform Resource Locator : adresse d'une route web."),
    ("WSGI", "Web Server Gateway Interface : interface d'exécution Python pour application web."),
]

FIGURES = [
    ("2.1", "Diagramme global des cas d'utilisation du système RH"),
    ("3.1", "Architecture applicative en couches"),
    ("3.2", "Diagramme de classes métier principal"),
    ("3.3", "Séquence de création et validation d'un shift"),
    ("3.4", "Séquence du pointage fondé sur le planning"),
    ("3.5", "Modèle relationnel synthétique"),
    ("4.1", "Organisation fonctionnelle du module Planning"),
    ("4.2", "Chaîne de validation technique"),
]

TABLES = [
    ("1.1", "Critique de l'existant et réponse proposée"),
    ("1.2", "Planning prévisionnel du projet"),
    ("2.1", "Acteurs du système"),
    ("2.2", "Besoins fonctionnels principaux"),
    ("2.3", "Cas d'utilisation : créer un planning"),
    ("2.4", "Cas d'utilisation : pointer l'entrée et la sortie"),
    ("3.1", "Choix technologiques et justification"),
    ("3.2", "Dictionnaire de données synthétique"),
    ("4.1", "Environnement de développement et d'exécution"),
    ("4.2", "Exceptions et validations gérées"),
    ("4.3", "Tests et vérifications réalisés"),
]

TOC = [
    ("Introduction générale", 1),
    ("Chapitre 1 : Présentation générale du projet", 2),
    ("1.1 Introduction", 2),
    ("1.2 Contexte général", 2),
    ("1.3 Problématique", 3),
    ("1.4 Étude de l’existant", 3),
    ("1.5 Objectifs du projet", 4),
    ("1.6 Méthodologie adoptée", 4),
    ("1.7 Conclusion", 4),
    ("Chapitre 2 : Analyse et spécification des besoins", 5),
    ("2.1 Introduction", 5),
    ("2.2 Acteurs du système", 5),
    ("2.3 Besoins fonctionnels", 6),
    ("2.4 Besoins non fonctionnels", 6),
    ("2.5 Diagramme de cas d’utilisation", 7),
    ("2.6 Description des principaux cas d’utilisation", 7),
    ("2.7 Conclusion", 7),
    ("Chapitre 3 : Conception et choix technologiques", 8),
    ("3.1 Introduction", 8),
    ("3.2 Architecture de l’application", 8),
    ("3.3 Modèle de données et diagramme de classes", 9),
    ("3.4 Diagrammes de séquence", 9),
    ("3.5 Modèle de base de données", 10),
    ("3.6 Choix technologiques", 10),
    ("3.7 Conclusion", 10),
    ("Chapitre 4 : Réalisation, tests, validation et déploiement", 11),
    ("4.1 Introduction", 11),
    ("4.2 Environnement de développement", 11),
    ("4.3 Fonctionnalités réalisées", 12),
    ("4.4 Module Planning", 12),
    ("4.5 Liaison Planning et Pointage", 12),
    ("4.6 Assistant Gemini", 13),
    ("4.7 Gestion des exceptions", 13),
    ("4.8 Tests et validation", 13),
    ("4.9 Déploiement", 14),
    ("4.10 Difficultés rencontrées", 14),
    ("4.11 Conclusion", 14),
    ("Conclusion générale", 15),
    ("Annexes", 16),
]


def build_front():
    front = []
    for title in ["Remerciements", "Résumé", "Mots-clés", "Abstract", "Keywords"]:
        front.append(h1(title))
        for paragraph in FRONT_MATTER[title]:
            add_par(front, paragraph)
        front.append(PageBreak())

    front.append(h1("Liste des figures"))
    for num, title in FIGURES:
        front.append(Paragraph(escape(f"Figure {num} : {title}"), styles["TOC"]))
        md.append(f"Figure {num} : {title}\n")
    front.append(PageBreak())

    front.append(h1("Liste des tableaux"))
    for num, title in TABLES:
        front.append(Paragraph(escape(f"Tableau {num} : {title}"), styles["TOC"]))
        md.append(f"Tableau {num} : {title}\n")
    front.append(PageBreak())

    front.append(h1("Liste des abréviations"))
    add_table(
        front,
        "",
        "Liste des abréviations",
        [["Abréviation", "Signification"]] + ABBREVIATIONS,
        col_widths=[3.1 * cm, TEXT_W - 3.1 * cm],
        font_size=8.7,
    )
    front.append(PageBreak())

    front.append(h1("Table des matières"))
    for item, page in TOC:
        indent = 0
        if item[:1].isdigit():
            indent = 12 if item.count(".") == 1 else 18
        style = ParagraphStyle("TOCItem", parent=styles["TOC"], leftIndent=indent)
        label = f"{item} {' .' * max(2, 58 - len(item))} {page}"
        front.append(Paragraph(escape(label), style))
    front.append(PageBreak())
    return front


def build_main():
    main = []

    main.append(h1("Introduction générale"))
    for paragraph in [
        "La gestion des ressources humaines occupe une place centrale dans le fonctionnement d'une organisation moderne. Elle ne se limite plus à l'enregistrement administratif des salariés ; elle couvre aussi le suivi des congés, les demandes internes, la planification du travail, le pointage, la formation, la communication RH, les réclamations, la paie et la traçabilité des décisions. Lorsque ces processus sont répartis entre des fichiers, des échanges informels ou des validations manuelles, les risques augmentent : perte d'information, erreurs de calcul, lenteur de traitement, manque de visibilité pour les managers et difficulté à justifier les décisions.",
        "Le projet présenté dans ce rapport répond à cette problématique par une plateforme web de gestion des ressources humaines développée avec Django. L'application est organisée autour des modules accounts, core et hr. Elle s'appuie sur le système d'authentification de Django, sur des profils applicatifs portant les rôles ADMIN, RESPONSABLE_RH, RESPONSABLE_HIERARCHIQUE et EMPLOYE, sur une base de données SQLite en environnement local, sur des templates HTML et sur des services métier chargés de sécuriser les traitements sensibles.",
        "Une attention particulière a été portée au module Planning, car il représente un besoin opérationnel fort dans une plateforme RH. La version enrichie permet de créer et consulter des shifts, de distinguer les plans normaux des plans permanents, de gérer des récurrences, d'utiliser des vues calendrier, d'appliquer des filtres compacts, de visualiser des indicateurs, de créer des plannings groupés et de relier les shifts au module Présence / Pointage. Ainsi, le calcul des retards, des sorties anticipées et des heures manquantes s'appuie sur la référence de planning réellement associée à l'employé.",
        "Le projet intègre également un assistant intelligent. L'assistant global utilise une logique de récupération de contexte autorisé avant l'appel éventuel à Gemini. L'assistant Planning, quant à lui, peut répondre à des questions opérationnelles sur les conflits, les heures planifiées ou les employés sans planning, et prépare une couche d'action contrôlée pour les utilisateurs RH ou administrateurs. Cette conception évite que le modèle d'IA modifie directement la base de données ; les validations restent assurées par le backend.",
        "La méthodologie adoptée est incrémentale. Le projet commence par l'étude du contexte RH et de l'existant, puis formalise les besoins, conçoit les entités et les scénarios, réalise les modules avec Django et vérifie les traitements par des tests ciblés. Le rapport est structuré en quatre chapitres. Le premier chapitre présente le contexte général, la problématique, les objectifs, l'étude de l'existant et la méthodologie. Le deuxième chapitre analyse les besoins, les acteurs et les cas d'utilisation. Le troisième chapitre expose la conception, l'architecture, le modèle de données et les choix technologiques. Le quatrième chapitre décrit la réalisation, les interfaces, les tests, la validation, le déploiement et les difficultés rencontrées.",
    ]:
        add_par(main, paragraph)
    main.append(PageBreak())

    chapter1(main)
    chapter2(main)
    chapter3(main)
    chapter4(main)
    conclusion_and_annexes(main)
    return main


def chapter1(main):
    main.append(h1("Chapitre 1 : Présentation générale du projet"))
    sections = [
        (
            "1.1 Introduction",
            [
                "Ce chapitre présente le cadre général du projet. Il situe le besoin RH auquel répond la plateforme, identifie les limites de l'existant, précise les objectifs attendus et explique la démarche de travail adoptée. Il permet ainsi de comprendre pourquoi une application RH centralisée est pertinente et pourquoi le module Planning a nécessité une attention particulière."
            ],
        ),
        (
            "1.2 Contexte général",
            [
                "Les services RH manipulent des données nombreuses et sensibles : identité des employés, affectations, responsables hiérarchiques, congés, documents, rémunération, formations, pointage et demandes internes. Dans l'application étudiée, ces informations sont regroupées dans une solution Django unique. Le dossier config contient la configuration, accounts porte l'identité et les rôles, core gère le tableau de bord et l'assistant global, tandis que hr concentre les modèles métier, les formulaires, les vues, les services, les permissions et les tests.",
                "L'application ne se limite pas à un CRUD d'employés. Elle couvre plusieurs processus de bout en bout : soumission et validation d'un congé, déduction du solde, création de documents, notifications, audit, pointage, gestion des points, boutique interne, réclamations, messagerie RH, tâches d'équipe, actualités et paie. Cette couverture fonctionnelle impose une conception rigoureuse pour garantir la cohérence des données et la confidentialité des informations personnelles.",
                "Le module Planning devient le centre opérationnel de l'organisation du temps. Il structure les shifts individuels, les plannings groupés et les plans permanents. Sa liaison avec le pointage permet de passer d'un simple enregistrement de présence à une analyse planifié/réalisé : heures attendues, heures travaillées, retard, sortie anticipée, manque horaire et heures supplémentaires.",
            ],
        ),
        (
            "1.3 Problématique",
            [
                "La problématique générale peut être formulée ainsi : comment concevoir une plateforme RH web capable de centraliser les processus administratifs, de sécuriser les accès selon les rôles, d'automatiser les traitements critiques et de fournir une vision fiable du planning et de la présence des employés ?",
                "Cette problématique se décline en plusieurs contraintes concrètes. Le système doit empêcher les incohérences de données, par exemple un congé avec une date de fin antérieure à la date de début, un solde négatif, une hiérarchie circulaire ou deux shifts qui se chevauchent pour le même employé. Il doit également empêcher les fuites d'informations : un employé ne doit pas consulter les données privées d'un autre employé, et un manager ne doit voir que son périmètre autorisé.",
                "Enfin, la plateforme doit rester exploitable dans une démonstration réelle. Les écrans ne doivent pas paraître vides, les messages d'erreur doivent être professionnels, les actions doivent être auditées lorsque nécessaire et l'interface doit permettre à un utilisateur RH de comprendre rapidement la situation.",
            ],
        ),
        (
            "1.4 Étude de l’existant",
            [
                "Dans un fonctionnement manuel, les informations RH sont souvent dispersées dans plusieurs fichiers, courriels ou conversations. Cette organisation crée des difficultés de suivi, car les validations ne sont pas toujours tracées, les documents peuvent être stockés sans contrôle d'accès et les responsables manquent d'indicateurs consolidés.",
                "L'existant applicatif initial avait déjà une base solide : authentification, employés, congés, demandes administratives, documents, notifications, pointage, planning, formations, réclamations, paie et audit. Toutefois, le module Planning devait être renforcé afin de devenir un vrai espace opérationnel. Les nouveaux besoins imposaient des plans permanents, des vues calendrier plus lisibles, une création groupée, des API prêtes pour l'assistant et une intégration plus directe avec le pointage.",
                "La solution actuelle répond à ces limites par une architecture Django structurée et par une séparation des responsabilités. Les règles critiques sont placées dans les modèles, formulaires et services. Les vues orchestrent les workflows et les templates affichent des données déjà filtrées selon le profil connecté.",
            ],
        ),
    ]
    for title, paragraphs in sections:
        main.append(h2(title))
        for paragraph in paragraphs:
            add_par(main, paragraph)
    add_table(
        main,
        "1.1",
        "Critique de l'existant et réponse proposée",
        [
            ["Limite identifiée", "Risque", "Réponse de la plateforme"],
            ["Données RH dispersées", "Perte d’information et doublons", "Centralisation des employés, demandes, documents, points et pointages dans les modèles Django."],
            ["Validation manuelle des congés", "Solde incohérent ou chevauchement", "Contrôles dans DemandeCongeForm, modèle DemandeConge et services transactionnels."],
            ["Planning peu exploitable", "Absence de référence pour le pointage", "PlanningShift, plans normaux/permanents, vues calendrier, API et lien avec Pointage."],
            ["Permissions uniquement visuelles", "Accès direct non autorisé", "Filtres queryset, décorateurs login_required/role_required et services de périmètre."],
            ["Absence d’aide contextuelle", "Difficulté à retrouver l’information", "Assistant RAG sécurisé, assistant Planning et réponses limitées au contexte autorisé."],
        ],
        col_widths=[4.0 * cm, 4.2 * cm, TEXT_W - 8.2 * cm],
    )
    main.append(h2("1.5 Objectifs du projet"))
    add_par(main, "Les objectifs du projet sont à la fois fonctionnels, techniques et pédagogiques. Fonctionnellement, il s'agit de proposer une plateforme RH intégrée, capable de couvrir les processus courants d'une organisation. Techniquement, il s'agit d'exploiter les mécanismes de Django pour produire une solution maintenable, testable et extensible. Pédagogiquement, le projet doit être défendable devant un jury : chaque règle importante doit pouvoir être reliée à un modèle, un formulaire, une vue, un service ou un test.")
    main.append(h2("1.6 Méthodologie adoptée"))
    add_par(main, "La démarche suivie est incrémentale. Chaque module est analysé, amélioré puis validé. Cette méthode convient à une application déjà existante, car elle évite de réécrire l'ensemble du système et permet de respecter les conventions du dépôt. Pour le Planning, l'analyse a d'abord porté sur les modèles, vues, formulaires, templates et scripts. Les améliorations ont ensuite été consolidées dans les services, l'interface et les tests.")
    add_par(main, "La méthode met aussi l'accent sur la validation. Les commandes Django permettent de vérifier la configuration, les migrations de test et les scénarios critiques. Les tests ciblés du Planning et de l'assistant global ont été exécutés pour confirmer les comportements sensibles : permissions, confidentialité, création de shift, plan permanent, conflits, calcul pointage et fallback Gemini.")
    add_table(
        main,
        "1.2",
        "Planning prévisionnel du projet",
        [
            ["Phase", "Travaux réalisés"],
            ["Analyse", "Lecture du dépôt, identification des modules, règles métier et contraintes de sécurité."],
            ["Spécification", "Définition des acteurs, besoins fonctionnels, besoins non fonctionnels et cas d’utilisation."],
            ["Conception", "Architecture Django, modèle de données, scénarios dynamiques, API et assistant."],
            ["Réalisation", "Amélioration du Planning, lien Pointage, vues calendrier, services, assistant et seed demo."],
            ["Validation", "Exécution de manage.py check, tests ciblés Planning et tests ciblés assistant."],
            ["Rédaction", "Production du rapport final conforme aux consignes données."],
        ],
        col_widths=[3.2 * cm, TEXT_W - 3.2 * cm],
    )
    main.append(h2("1.7 Conclusion"))
    add_par(main, "Ce chapitre a présenté le contexte général, la problématique et la démarche adoptée. La plateforme répond à un besoin de centralisation, de fiabilité et de sécurité des processus RH. Le module Planning constitue une évolution importante, car il transforme la gestion du temps en une référence exploitable pour le pointage et pour le pilotage RH. Le chapitre suivant formalise les besoins fonctionnels, non fonctionnels et les principaux cas d'utilisation.")
    main.append(PageBreak())


def chapter2(main):
    main.append(h1("Chapitre 2 : Analyse et spécification des besoins"))
    main.append(h2("2.1 Introduction"))
    add_par(main, "Ce chapitre présente les besoins de la plateforme. Il identifie les acteurs, décrit les fonctionnalités attendues, précise les exigences non fonctionnelles et détaille les cas d'utilisation les plus importants. L'analyse s'appuie sur le comportement réel du code Django, notamment les modèles, les formulaires, les services, les vues, les routes et les tests.")
    main.append(h2("2.2 Acteurs du système"))
    add_par(main, "Le système distingue quatre profils principaux. L'administrateur possède le périmètre le plus large. Le responsable RH gère les opérations RH courantes. Le responsable hiérarchique consulte son équipe et suit les informations rattachées à ses collaborateurs. L'employé consulte ses données personnelles et réalise ses propres actions, comme le pointage ou la soumission de demandes.")
    add_table(
        main,
        "2.1",
        "Acteurs du système",
        [
            ["Acteur", "Rôle dans la plateforme", "Accès principal"],
            ["Administrateur", "Supervise les modules sensibles et l’administration générale.", "Utilisateurs, paie, audit, référentiels, planning, statistiques."],
            ["Responsable RH", "Traite les processus RH et pilote les opérations.", "Employés, congés, demandes, documents, planning, formations, réclamations."],
            ["Responsable hiérarchique", "Suit son périmètre d’équipe.", "Planning visible, pointages d’équipe, tâches, demandes liées à ses collaborateurs."],
            ["Employé", "Utilise les services RH pour ses propres données.", "Pointage personnel, demandes, formations, boutique, planning personnel, messages RH."],
        ],
        col_widths=[3.3 * cm, 6.2 * cm, TEXT_W - 9.5 * cm],
    )
    main.append(h2("2.3 Besoins fonctionnels"))
    add_par(main, "Les besoins fonctionnels couvrent l'ensemble des processus RH. L'application doit authentifier les utilisateurs, gérer les profils actifs, organiser les employés par département, service, poste et responsable, traiter les congés, suivre les documents, calculer les points, permettre le pointage, produire des tableaux de bord et sécuriser la consultation des données selon les rôles.")
    add_par(main, "Pour le Planning, les besoins sont plus spécifiques. L'utilisateur RH doit pouvoir créer un shift individuel ou groupé, sélectionner une cible par service, département, entreprise ou liste d'employés, choisir un statut, définir une pause, consulter les conflits, copier une période, déplacer ou redimensionner un shift normal et accéder à des vues adaptées à différents horizons temporels. Le système doit aussi accepter les plans permanents, utiles pour modéliser le rythme standard d'une entreprise sans imposer une date de fin artificielle.")
    add_table(
        main,
        "2.2",
        "Besoins fonctionnels principaux",
        [
            ["Module", "Besoins fonctionnels"],
            ["Authentification", "Connexion, profil actif, rôles applicatifs, redirection vers le tableau de bord."],
            ["Employés et organisation", "Création, modification, archivage, affectation à un département, service, poste et responsable."],
            ["Congés", "Soumission, validation, refus, annulation, solde, mouvement de solde, double validation manager/RH."],
            ["Documents", "Upload, contrôle d’extension, taille maximale, téléchargement sécurisé et archivage logique."],
            ["Planning", "Shifts normaux, plans permanents, récurrence, filtres, vues calendrier, création groupée, API, conflits."],
            ["Pointage", "Entrée, sortie, total d’heures, retard, sortie anticipée, heures manquantes, points calculés."],
            ["Assistant", "RAG sécurisé, refus hors permission, fallback local, assistant Planning pour résumés et conflits."],
        ],
        col_widths=[3.4 * cm, TEXT_W - 3.4 * cm],
    )
    main.append(h2("2.4 Besoins non fonctionnels"))
    add_bullets(
        main,
        [
            "Sécurité : les données doivent être filtrées côté backend selon le rôle et le périmètre de l'utilisateur.",
            "Fiabilité : les opérations critiques doivent être validées par les modèles, les formulaires ou les services.",
            "Traçabilité : les actions importantes doivent alimenter l'historique d'audit et les notifications lorsque cela est pertinent.",
            "Ergonomie : les interfaces doivent être compactes, lisibles, responsives et cohérentes avec le design existant.",
            "Maintenabilité : les traitements complexes doivent rester dans les services plutôt que dans les templates.",
            "Testabilité : les comportements sensibles doivent être vérifiés par des tests Django ciblés.",
            "Confidentialité IA : l'assistant ne doit recevoir que le contexte autorisé et doit refuser les demandes d'accès privé ou les tentatives d'injection.",
        ],
    )
    main.append(h2("2.5 Diagramme de cas d'utilisation"))
    add_par(main, "Le diagramme suivant synthétise les interactions entre les acteurs et les principaux modules. Il met en évidence la place du Planning comme passerelle entre la gestion du temps, le pointage et les statistiques RH.")
    add_figure(
        main,
        "2.1",
        "Diagramme global des cas d'utilisation du système RH",
        [
            ["Employé", "S’authentifier\nConsulter ses données\nPointer entrée/sortie\nSoumettre demandes\nConsulter planning"],
            ["Manager", "Consulter équipe\nSuivre pointages\nVoir planning d’équipe\nSuivre tâches"],
            ["Responsable RH", "Gérer employés\nTraiter demandes\nCréer planning\nGérer documents\nAnalyser indicateurs"],
            ["Administrateur", "Administrer rôles\nConsulter audit\nGérer paie\nSuperviser plateforme"],
            ["Assistant Gemini", "Répondre avec contexte autorisé\nAider sur Planning\nRefuser hors permission"],
        ],
        col_widths=[4.0 * cm, TEXT_W - 4.0 * cm],
    )
    main.append(h2("2.6 Description des principaux cas d'utilisation"))
    add_table(
        main,
        "2.3",
        "Cas d’utilisation : créer un planning",
        [
            ["Élément", "Description"],
            ["Acteur principal", "Responsable RH ou administrateur."],
            ["Objectif", "Créer un shift normal ou un plan permanent pour un employé, un service, un département ou un groupe."],
            ["Préconditions", "Utilisateur connecté, rôle autorisé, dates valides, employé actif si le shift est assigné."],
            ["Scénario nominal", "L’acteur choisit la cible, renseigne les horaires, la pause, le statut et enregistre. Le service crée les shifts, audite l’action et notifie l’employé lorsque nécessaire."],
            ["Scénarios alternatifs", "Dates invalides, pause incohérente, chevauchement, congé validé ou plan permanent déjà actif : la création est refusée avec un message clair."],
            ["Postconditions", "Le planning est enregistré et apparaît dans les vues calendrier et les API."],
        ],
        col_widths=[4.0 * cm, TEXT_W - 4.0 * cm],
    )
    add_table(
        main,
        "2.4",
        "Cas d'utilisation : pointer l'entrée et la sortie",
        [
            ["Élément", "Description"],
            ["Acteur principal", "Employé."],
            ["Objectif", "Enregistrer la présence du jour et calculer les heures réellement travaillées."],
            ["Préconditions", "Utilisateur connecté, profil lié à un employé, aucun pointage déjà ouvert."],
            ["Scénario nominal", "L’employé pointe l’entrée. Le système associe le shift planifié si disponible. À la sortie, le service calcule total, retard, sortie anticipée, heures manquantes et points."],
            ["Scénarios alternatifs", "Double pointage, sortie sans entrée ou sortie avant entrée : l’action est refusée. Si aucun shift n’existe, un fallback sécurisé évite le calcul erroné des heures manquantes."],
            ["Postconditions", "Le pointage est fermé, le statut est mis à jour et les points sont enregistrés si applicable."],
        ],
        col_widths=[4.0 * cm, TEXT_W - 4.0 * cm],
    )
    main.append(h2("2.7 Conclusion"))
    add_par(main, "Ce chapitre a formalisé les besoins du système et les rôles des utilisateurs. L'analyse montre que la plateforme vise une couverture RH large, mais que le Planning et sa liaison avec le Pointage constituent l'axe le plus structurant des nouvelles fonctionnalités. Le chapitre suivant présente la conception permettant de répondre à ces besoins.")
    main.append(PageBreak())


def chapter3(main):
    main.append(h1("Chapitre 3 : Conception et choix technologiques"))
    main.append(h2("3.1 Introduction"))
    add_par(main, "Ce chapitre présente la conception technique et fonctionnelle de la plateforme. Il détaille l'architecture Django, le modèle de données, les scénarios dynamiques, la base de données et les choix technologiques. L'objectif est de montrer comment les besoins exprimés sont traduits en composants logiciels cohérents.")
    main.append(h2("3.2 Architecture de l'application"))
    add_par(main, "L'architecture suit une organisation en couches. Les templates et fichiers statiques composent l'interface utilisateur. Les routes Django redirigent les requêtes vers les vues. Les vues récupèrent le profil connecté, appliquent les filtres et orchestrent les services. Les formulaires et modèles valident les données. Les services métier regroupent les traitements critiques, notamment les transactions de points, les soldes de congés, le Planning et le Pointage. L'ORM assure la persistance dans SQLite en développement.")
    add_figure(
        main,
        "3.1",
        "Architecture applicative en couches",
        [
            ["Interface utilisateur", "Templates Django, Bootstrap, CSS, JavaScript, widgets assistant"],
            ["Routage", "config.urls, hr.urls, core.urls, accounts.urls"],
            ["Vues", "core.views, hr.views, accounts.views"],
            ["Services métier", "hr.services, hr.planning_services, hr.planning_assistant, core.ai_assistant"],
            ["Données", "Modèles Django, ORM, migrations, SQLite local"],
            ["Services externes", "Gemini via google-genai, Brevo en configuration optionnelle"],
        ],
        col_widths=[4.2 * cm, TEXT_W - 4.2 * cm],
    )
    main.append(h2("3.3 Modèle de données et diagramme de classes"))
    add_par(main, "La classe Employe est le pivot du domaine. Elle est reliée aux départements, services, postes, responsables, congés, documents, pointages, shifts, formations, conversations RH, réclamations, rémunérations et comptes de points. Le modèle UtilisateurProfile rattache un compte Django à un rôle et à un employé. PlanningShift représente les shifts et plans permanents. Pointage référence éventuellement un PlanningShift pour permettre les calculs planifié/réalisé.")
    add_figure(
        main,
        "3.2",
        "Diagramme de classes métier principal",
        [
            ["UtilisateurProfile", "role\nactif\nemploye"],
            ["Employe", "matricule\nnom/prenom\ndepartement\nservice\nresponsable"],
            ["PlanningShift", "plan_type\nrecurrence_rule\ndate_debut/date_fin\npause\nstatut"],
            ["Pointage", "shift\nheure_entree\nheure_sortie\ntotal_heures\nstatut"],
            ["DemandeConge", "dates\nstatut\nworkflow manager/RH\nsolde"],
            ["ComptePoints", "solde_points\ntransactions"],
        ],
        col_widths=[3.0 * cm, TEXT_W - 3.0 * cm],
    )
    add_table(
        main,
        "3.2",
        "Dictionnaire de données synthétique",
        [
            ["Entité", "Attributs clés", "Rôle"],
            ["UtilisateurProfile", "user, role, actif, employe", "Porte le rôle applicatif et rattache un compte Django à un employé."],
            ["Employe", "matricule, nom, email, departement, service, responsable", "Représente le salarié et la structure hiérarchique."],
            ["PlanningShift", "titre, employe, date_debut, date_fin, plan_type, recurrence_rule, pause_minutes", "Planifie les shifts normaux et les plans permanents."],
            ["Pointage", "employe, shift, date, heure_entree, heure_sortie, total_heures, statut", "Enregistre la présence et calcule le réalisé par rapport au planning."],
            ["DemandeConge", "type, date_debut, date_fin, statut, employe", "Gère les absences, validations et solde de congés."],
            ["TacheEquipe", "titre, mode_affectation, employe, manager, shift, statut", "Suit les tâches opérationnelles et peut être liée à un shift."],
            ["ConversationRH", "sujet, employe, responsable_rh, statut, priorité", "Gère les échanges RH et tickets internes."],
            ["HistoriqueAction", "action, details, utilisateur, entite", "Assure l’audit des actions importantes."],
        ],
        col_widths=[3.1 * cm, 5.2 * cm, TEXT_W - 8.3 * cm],
        font_size=8.0,
    )
    main.append(h2("3.4 Diagrammes de séquence"))
    add_par(main, "Les deux séquences principales concernent la création d'un shift et le pointage. Elles montrent que l'interface ne modifie pas directement les données : la requête passe par une vue, puis par un service, puis par les validations du modèle.")
    add_figure(
        main,
        "3.3",
        "Séquence de création et validation d'un shift",
        [
            ["1", "RH/Admin saisit le planning dans l’offcanvas ou le formulaire groupé."],
            ["2", "La vue planning_api_shifts ou planning_create lit le payload et le profil."],
            ["3", "create_shift ou bulk_create_shifts vérifie les permissions."],
            ["4", "PlanningShift.full_clean bloque dates invalides, chevauchements, congés et plan permanent doublon."],
            ["5", "Le shift est sauvegardé, audité et notifié si nécessaire."],
        ],
        col_widths=[1.1 * cm, TEXT_W - 1.1 * cm],
    )
    add_figure(
        main,
        "3.4",
        "Séquence du pointage fondé sur le planning",
        [
            ["1", "L’employé pointe son entrée."],
            ["2", "pointer_entree recherche le shift normal actif, puis un plan permanent applicable."],
            ["3", "Le pointage est créé avec la référence PlanningShift si elle existe."],
            ["4", "À la sortie, pointer_sortie calcule la fenêtre prévue, les heures, le retard et la sortie anticipée."],
            ["5", "Le commentaire détaille les écarts et les points sont appliqués via TransactionPoints."],
        ],
        col_widths=[1.1 * cm, TEXT_W - 1.1 * cm],
    )
    main.append(h2("3.5 Modèle de base de données"))
    add_par(main, "Le modèle relationnel repose sur les clés étrangères Django. Les relations les plus importantes sont : UtilisateurProfile vers Employe, Employe vers Departement, Service, Poste et responsable, PlanningShift vers Employe, Departement et Service, Pointage vers Employe et PlanningShift, DemandeConge vers Employe, TacheEquipe vers PlanningShift et Employe, et HistoriqueAction vers UtilisateurProfile.")
    add_figure(
        main,
        "3.5",
        "Modèle relationnel synthétique",
        [
            ["accounts_utilisateurprofile", "1 -- 0..1", "hr_employe"],
            ["hr_employe", "1 -- n", "hr_planningshift"],
            ["hr_planningshift", "1 -- n", "hr_pointage"],
            ["hr_employe", "1 -- n", "hr_demandeconge"],
            ["hr_employe", "1 -- 1", "hr_comptepoints"],
            ["hr_comptepoints", "1 -- n", "hr_transactionpoints"],
        ],
        col_widths=[5.0 * cm, 2.5 * cm, TEXT_W - 7.5 * cm],
    )
    main.append(h2("3.6 Choix technologiques"))
    add_par(main, "Les technologies ont été choisies pour leur cohérence avec le dépôt existant et leur adéquation à un projet RH. Django offre un ORM fiable, un système d'authentification, des formulaires, des migrations, des vues et des tests. SQLite facilite le développement local. Bootstrap et Bootstrap Icons accélèrent la réalisation d'une interface professionnelle. google-genai permet l'appel optionnel à Gemini sans exposer la clé dans le code.")
    add_table(
        main,
        "3.1",
        "Choix technologiques et justification",
        [
            ["Technologie", "Utilisation", "Justification"],
            ["Python 3.12.10", "Langage principal", "Lisible, adapté à Django et aux scripts de gestion."],
            ["Django 5.0.6", "Framework web", "ORM, sécurité, migrations, templates, tests et authentification intégrés."],
            ["SQLite", "Base locale", "Simple pour développement, démonstration et tests."],
            ["Bootstrap 5.3", "Interface", "Composants visuels cohérents et responsive."],
            ["Bootstrap Icons", "Icônes", "Lisibilité des actions et navigation compacte."],
            ["JavaScript natif", "Interactions Planning", "Drag-and-drop, API fetch, assistant, modal et offcanvas sans dépendance lourde."],
            ["google-genai", "Assistant Gemini", "Intégration IA contrôlée par variables d’environnement."],
            ["ReportLab / pypdf", "Génération du présent rapport", "Production du PDF et conservation de la page de garde originale."],
        ],
        col_widths=[3.4 * cm, 4.4 * cm, TEXT_W - 7.8 * cm],
        font_size=8.0,
    )
    main.append(h2("3.7 Conclusion"))
    add_par(main, "La conception repose sur une séparation claire entre interface, vues, services, validations et modèles. Cette organisation permet de sécuriser les données, de tester les règles critiques et de faire évoluer le Planning sans fragiliser les autres modules. Le chapitre suivant présente la réalisation concrète, les interfaces, les tests et le déploiement.")
    main.append(PageBreak())


def chapter4(main):
    main.append(h1("Chapitre 4 : Réalisation, tests, validation et déploiement"))
    main.append(h2("4.1 Introduction"))
    add_par(main, "Ce chapitre décrit la réalisation concrète de la plateforme et plus particulièrement l'évolution du module Planning. Il présente l'environnement de développement, les fonctionnalités livrées, les contrôles d'exception, les tests effectués, la stratégie de déploiement et les difficultés rencontrées.")
    main.append(h2("4.2 Environnement de développement"))
    add_par(main, "Le projet est exécuté localement sur Windows dans le répertoire HR_django. La configuration Django utilise la langue française, le fuseau horaire Africa/Casablanca, SQLite en base locale, les fichiers statiques dans static et les fichiers téléversés dans media. Les variables liées à Gemini, Brevo et aux limites de contexte sont lues depuis l'environnement.")
    add_table(
        main,
        "4.1",
        "Environnement de développement et d'exécution",
        [
            ["Élément", "Valeur observée"],
            ["Système", "Windows, projet situé dans OneDrive/Desktop/HR_django."],
            ["Python", "Python 3.12.10."],
            ["Framework", "Django 5.0.6."],
            ["Dépendances principales", "Pillow 10.3.0, google-genai 1.51.0."],
            ["Base locale", "SQLite via db.sqlite3."],
            ["Fuseau horaire", "Africa/Casablanca."],
            ["Variables IA", "GEMINI_API_KEY ou GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_MS, RAG_MAX_CONTEXT_ITEMS, RAG_MAX_CONTEXT_TOKENS."],
        ],
        col_widths=[4.0 * cm, TEXT_W - 4.0 * cm],
    )
    main.append(h2("4.3 Fonctionnalités réalisées"))
    add_par(main, "La plateforme propose un ensemble complet de modules RH : tableau de bord, gestion des employés, organisation interne, congés, demandes administratives, documents, notifications, audit, pointage, planning, tâches d'équipe, formations, messages RH, actualités, boutique interne, réclamations, points, paie et assistant. Les modules communiquent entre eux : un congé validé influence la disponibilité d'un employé, un shift peut être lié à un pointage, une tâche peut être rattachée à un shift et les actions importantes peuvent produire notifications ou audit.")
    add_par(main, "La refonte visuelle centralisée améliore l'expérience utilisateur. La navigation latérale regroupe les sous-modules du Planning, les cartes statistiques sont compactes, les statuts sont colorés et les écrans utilisent des composants cohérents. Cette cohérence est importante pour une application de gestion, car l'utilisateur doit pouvoir scanner rapidement les informations sans être distrait par une interface instable.")
    main.append(h2("4.4 Module Planning"))
    add_par(main, "Le module Planning est accessible par une entrée principale et plusieurs sous-onglets : Overview, Calendar, Daily, Weekly, Bi-weekly, Monthly, Timesheets, Shift Management, Attendance, Time Off, Tasks, Approvals, Reports et Settings. Cette organisation donne une vision progressive : synthèse, calendrier, planification opérationnelle, feuilles de temps, congés, tâches, rapports et paramètres.")
    add_par(main, "Le modèle PlanningShift distingue deux types de plans. Le plan normal possède un début et une fin. Il sert aux shifts ponctuels ou limités dans le temps. Le plan permanent représente un rythme standard, par exemple un horaire lundi-vendredi, et peut fonctionner sans date de fin grâce à permanent_end_time. Les récurrences disponibles sont daily, weekdays, weekly, biweekly et monthly. Le code empêche un employé d'avoir plusieurs plans permanents actifs et refuse les récurrences sur les plans normaux afin d'éviter les ambiguïtés.")
    add_par(main, "L'interface propose des statistiques compactes : shifts planifiés, plans permanents, demandes en attente, retards, congés validés, heures planifiées et alertes. Les filtres incluent période, recherche, employé, département, service, statut, type de planning et niveau de conflit. Les vues calendrier utilisent des blocs colorés, des indicateurs +X more, un offcanvas d'édition, un modal de détail, des boutons de redimensionnement et un drag-and-drop pour déplacer les shifts normaux.")
    add_figure(
        main,
        "4.1",
        "Organisation fonctionnelle du module Planning",
        [
            ["Vue", "Rôle"],
            ["Overview", "Résumé opérationnel, alertes d’heures, indicateurs rapides."],
            ["Calendar / Daily / Weekly", "Lecture visuelle des shifts par jour, semaine ou employé."],
            ["Bi-weekly / Monthly", "Vision plus longue pour rotations et plans récurrents."],
            ["Timesheets / Attendance", "Comparaison entre planning et pointage."],
            ["Leave / Tasks", "Disponibilités, congés et tâches liées au planning."],
            ["Reports / Settings", "Synthèses, exports prévus, paramètres et limites actuelles."],
        ],
        col_widths=[4.2 * cm, TEXT_W - 4.2 * cm],
    )
    main.append(h2("4.5 Liaison Planning et Pointage"))
    add_par(main, "La liaison entre Planning et Pointage est un apport central. Lorsqu'un employé pointe l'entrée, le service pointer_entree cherche d'abord un shift normal publié couvrant la période courante. S'il n'en trouve pas, il recherche un plan permanent applicable au jour. Le pointage conserve alors une référence vers PlanningShift, ce qui permet au calcul de sortie de comparer le réel au prévu.")
    add_par(main, "À la sortie, pointer_sortie calcule la fenêtre attendue à partir du shift associé ou, à défaut, des paramètres officiels de pointage. Le service calcule les heures travaillées, le retard, la sortie anticipée, les heures manquantes et les points. Le commentaire du pointage conserve une trace lisible de ces écarts. Si aucun shift n'est trouvé, la fonction pointage_breakdown retourne un avertissement professionnel et ne calcule pas d'heures manquantes artificielles.")
    main.append(h2("4.6 Assistant Gemini"))
    add_par(main, "Deux niveaux d'assistance existent. L'assistant global, exposé par core.views.chatbot_api, récupère un contexte autorisé selon le rôle de l'utilisateur, refuse les demandes sensibles ou les tentatives d'injection, puis appelle Gemini si la configuration est disponible. En cas d'absence de clé ou d'erreur, il fournit une réponse déterministe fondée sur le contexte récupéré.")
    add_par(main, "L'assistant Planning, exposé par planning_api_assistant, est spécialisé dans les besoins opérationnels du planning. Il peut répondre localement aux demandes simples : afficher les conflits, identifier les employés sans planning et résumer les heures planifiées. Pour les actions plus complexes, Gemini est sollicité pour produire une intention structurée, mais l'exécution reste contrôlée par le backend. Les employés ne peuvent pas utiliser l'assistant pour consulter les informations privées d'autres employés, et les mutations sont réservées aux RH/Admin.")
    main.append(h2("4.7 Gestion des exceptions"))
    add_table(
        main,
        "4.2",
        "Exceptions et validations gérées",
        [
            ["Catégorie", "Traitement réalisé"],
            ["Dates invalides", "Début dans le passé pour plan normal, fin obligatoire, fin avant début et shift de nuit non supporté sont refusés."],
            ["Pause incohérente", "Pause plus longue que le shift, pause sans durée ou hors intervalle refusée."],
            ["Conflits planning", "Chevauchement de shifts normaux et congé validé détectés."],
            ["Plan permanent", "Heure de fin standard obligatoire et un seul plan permanent actif par employé."],
            ["Permissions", "Création, modification, déplacement et suppression réservés aux RH/Admin."],
            ["Pointage sans shift", "Avertissement clair et absence de calcul d’heures manquantes erroné."],
            ["Assistant", "Message vide refusé, accès privé refusé, fallback si Gemini indisponible."],
            ["API", "Réponses JSON homogènes : ok, data, errors, message."],
        ],
        col_widths=[4.0 * cm, TEXT_W - 4.0 * cm],
        font_size=8.1,
    )
    main.append(h2("4.8 Tests et validation"))
    add_par(main, "Les vérifications ont été effectuées directement dans l'environnement du projet. La commande python manage.py check a confirmé l'absence de problème système. Les tests ciblés du module Planning ont validé les scénarios critiques : accès par rôle, sous-onglets, création de shift, plan permanent, récurrences, rejet des cas invalides, rapports, modal de détail, lien pointage, permissions, déplacement, redimensionnement, création groupée, copie, conflits, disponibilité et assistant. Les tests ciblés de l'assistant global ont validé la confidentialité, le refus des mutations, la protection contre l'injection, la navigation et les règles d'accès.")
    add_table(
        main,
        "4.3",
        "Tests et vérifications réalisés",
        [
            ["Commande ou scénario", "Résultat"],
            ["python manage.py check", "Aucun problème système détecté."],
            ["python manage.py test hr.tests.PlanningModuleUpgradeTests --verbosity 2", "15 tests exécutés, 15 réussis, durée environ 90,5 s."],
            ["python manage.py test core.tests --verbosity 2", "12 tests exécutés, 12 réussis, durée environ 65,1 s."],
            ["python manage.py test", "La suite complète a dépassé la fenêtre d’exécution de cinq minutes dans cette session ; elle doit être relancée hors contrainte de temps avant impression finale."],
        ],
        col_widths=[6.6 * cm, TEXT_W - 6.6 * cm],
        font_size=8.1,
    )
    add_figure(
        main,
        "4.2",
        "Chaîne de validation technique",
        [
            ["Saisie utilisateur", "Formulaires HTML / JSON API"],
            ["Contrôle vue", "Profil, rôle, périmètre, CSRF, méthode HTTP"],
            ["Service métier", "Transactions, audit, notifications, parsing sécurisé"],
            ["Modèle Django", "full_clean, contraintes métier, relations ORM"],
            ["Tests", "Cas nominaux, refus, confidentialité, assistant, pointage"],
        ],
        col_widths=[4.2 * cm, TEXT_W - 4.2 * cm],
    )
    main.append(h2("4.9 Déploiement"))
    add_par(main, "Le projet fonctionne localement avec SQLite. Pour un déploiement réel, plusieurs adaptations sont nécessaires : désactiver DEBUG, externaliser SECRET_KEY, configurer ALLOWED_HOSTS, utiliser une base de données serveur comme PostgreSQL, collecter les fichiers statiques, gérer les médias, fournir les variables GEMINI_API_KEY ou GOOGLE_API_KEY si l'assistant doit appeler Gemini, et sécuriser les clés Brevo si les courriels de vérification sont activés.")
    add_par(main, "Le déploiement doit suivre une procédure reproductible : création de l'environnement virtuel, installation des dépendances, migrations, chargement éventuel des données de démonstration, création d'un compte administrateur, puis lancement par un serveur compatible WSGI/ASGI. Les commandes de seed sont utiles en démonstration ; seed_demo_rh crée des données professionnelles, des plannings permanents et des rotations normales avec des identifiants de démonstration.")
    main.append(h2("4.10 Difficultés rencontrées"))
    add_bullets(
        main,
        [
            "Transformer un Planning simple en module opérationnel sans perturber les autres modules RH.",
            "Garder les validations critiques côté backend afin d'éviter les contournements par API directe.",
            "Relier le pointage au planning tout en conservant un fallback sécurisé lorsqu'aucun shift n'existe.",
            "Intégrer Gemini sans exposer de clé API et sans donner au modèle un accès direct à la base de données.",
            "Préserver la lisibilité de l'interface malgré le nombre élevé de sous-vues, filtres et indicateurs.",
            "Tester les comportements sensibles dans un environnement local où la suite complète dépasse la fenêtre d'exécution disponible.",
        ],
    )
    main.append(h2("4.11 Conclusion"))
    add_par(main, "Ce chapitre a présenté la réalisation concrète de la plateforme et les améliorations du module Planning. Les fonctionnalités développées forment un ensemble cohérent : gestion des shifts, plans permanents, filtres, vues calendrier, API, assistant, données de démonstration et calcul de présence basé sur le planning. Les tests ciblés confirment les scénarios principaux et les limites restantes sont clairement identifiées pour les évolutions futures.")
    main.append(PageBreak())


def conclusion_and_annexes(main):
    main.append(h1("Conclusion générale"))
    for paragraph in [
        "Ce projet a permis de concevoir et de réaliser une plateforme web de gestion des ressources humaines avec Django. La solution centralise les données et les processus RH essentiels : employés, organisation, congés, demandes administratives, documents, notifications, audit, pointage, planning, tâches, formations, messagerie RH, actualités, boutique interne, réclamations, points et paie. Elle répond ainsi à un besoin réel de centralisation, de fiabilité, de traçabilité et de sécurité.",
        "L'amélioration la plus importante concerne le module Planning. Celui-ci ne se limite plus à une liste de shifts ; il devient un espace de pilotage avec plans normaux, plans permanents, récurrences, statistiques, filtres, calendrier, création groupée, API et assistant spécialisé. Sa liaison avec le module Pointage permet de calculer les écarts entre le temps prévu et le temps réellement travaillé, ce qui rend la présence beaucoup plus exploitable pour les responsables RH.",
        "Les résultats obtenus montrent une application riche et défendable techniquement. Les règles métier importantes sont placées dans des modèles, formulaires et services. Les permissions ne reposent pas uniquement sur l'affichage des boutons ; elles sont également appliquées côté backend. L'assistant Gemini est encadré par une récupération de contexte autorisé, par des refus de sécurité et par un fallback local. Les données de démonstration rendent les interfaces vivantes tout en gardant une logique idempotente.",
        "Certaines limites restent néanmoins présentes. Les exports PDF, CSV et Excel du module Planning sont encore affichés comme non configurés. Le workflow d'approbation Planning est préparé mais non activé. Les shifts de nuit ne sont pas supportés dans l'état actuel ; ils doivent être découpés ou faire l'objet d'une évolution spécifique. La création et modification du Planning sont réservées aux profils RH/Admin, tandis que les managers disposent surtout d'une consultation de leur périmètre. Enfin, le passage en production nécessite une configuration plus stricte que l'environnement local, notamment pour la base de données, les secrets, les médias et les hôtes autorisés.",
        "Les perspectives d'amélioration consistent à ajouter les exports opérationnels, activer un workflow d'approbation, enrichir la gestion des shifts de nuit, permettre des droits de modification limités aux managers selon leur périmètre, améliorer les rapports de présence, renforcer les tests de bout en bout et préparer un déploiement avec PostgreSQL. En conclusion, la plateforme constitue une base solide pour une gestion RH intégrée, moderne et évolutive.",
    ]:
        add_par(main, paragraph)
    main.append(PageBreak())

    main.append(h1("Annexes"))
    main.append(h2("Annexe A : Routes Planning principales"))
    add_table(
        main,
        "A.1",
        "Routes Planning principales",
        [
            ["Route", "Rôle"],
            ["/planning", "Page principale du module Planning et sous-onglets."],
            ["/planning/creer", "Création groupée via formulaire classique."],
            ["/planning/api/shifts", "Liste et création de shifts en JSON."],
            ["/planning/api/shifts/<id>", "Détail, mise à jour ou annulation d’un shift."],
            ["/planning/api/shifts/<id>/move", "Déplacement d’un shift normal."],
            ["/planning/api/shifts/<id>/resize", "Redimensionnement d’un shift normal."],
            ["/planning/api/bulk", "Création groupée par cible."],
            ["/planning/api/copy", "Copie d’une période de planning."],
            ["/planning/api/conflicts", "Détection de conflits."],
            ["/planning/api/summary", "Synthèse statistique."],
            ["/planning/api/available-employees", "Employés disponibles sur une période."],
            ["/planning/api/assistant", "Assistant spécialisé Planning."],
        ],
        col_widths=[6.2 * cm, TEXT_W - 6.2 * cm],
        font_size=8.0,
    )
    main.append(h2("Annexe B : Commandes utiles"))
    add_bullets(
        main,
        [
            "python -m venv .venv",
            ".\\.venv\\Scripts\\activate",
            "pip install -r requirements.txt",
            "python manage.py migrate",
            "python manage.py seed_demo_rh",
            "python manage.py check",
            "python manage.py test hr.tests.PlanningModuleUpgradeTests --verbosity 2",
            "python manage.py test core.tests --verbosity 2",
            "python manage.py runserver",
        ],
    )


def build_pdf(path, story, footer):
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=RIGHT,
        leftMargin=LEFT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def merge_pdfs():
    writer = PdfWriter()
    for pdf in [cover_pdf, front_pdf, main_pdf]:
        reader = PdfReader(str(pdf))
        for page in reader.pages:
            writer.add_page(page)
    with final_pdf.open("wb") as handle:
        writer.write(handle)


def main():
    front = build_front()
    body = build_main()
    build_pdf(front_pdf, front, front_footer)
    build_pdf(main_pdf, body, main_footer)
    merge_pdfs()
    md.insert(
        0,
        "# Rapport de Projet de Fin d'Année - Plateforme RH Django\n\n"
        "Note : le PDF final utilise la page de garde originale extraite de l'ancien rapport.\n\n",
    )
    md_path.write_text("\n".join(md), encoding="utf-8")
    page_count = len(PdfReader(str(final_pdf)).pages)
    print(f"final_pdf={final_pdf}")
    print(f"markdown_source={md_path}")
    print(f"pages={page_count}")


if __name__ == "__main__":
    main()
