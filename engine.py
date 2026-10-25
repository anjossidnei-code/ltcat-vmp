# -*- coding: utf-8 -*-
"""Motor de geração dos LTCAT (gerado a partir do gerador validado). Não editar à mão sem necessidade."""
from reportlab.platypus import Image
import os
HDR = ['']
FOOT = ['']
FONTDIR = ['C:/Windows/Fonts/']
# -*- coding: utf-8 -*-
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, KeepTogether, PageBreak)
from reportlab.pdfgen import canvas

F = FONTDIR[0]

# Carregamento robusto das fontes: funciona no PC (Calibri do Windows) E na nuvem
# (servidor Linux do Streamlit, que não tem Calibri — usa DejaVu/Liberation). Para cada
# estilo tenta, em ordem: pasta local 'fonts' (Calibri ou Carlito) -> Calibri do Windows
# -> DejaVu/Liberation do Linux. Se faltar o arquivo exato de um estilo, reusa o regular,
# evitando que o 'import engine' quebre por causa de fonte ausente.
_AQUI = os.path.dirname(os.path.abspath(__file__))

def _1o_existente(caminhos):
    for c in caminhos:
        if c and os.path.exists(c):
            return c
    return None

_FONTES = {
    "Cal":    ["calibri.ttf",  "Carlito-Regular.ttf",    "C:/Windows/Fonts/calibri.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
    "Cal-B":  ["calibrib.ttf", "Carlito-Bold.ttf",       "C:/Windows/Fonts/calibrib.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    "Cal-I":  ["calibrii.ttf", "Carlito-Italic.ttf",     "C:/Windows/Fonts/calibrii.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"],
    "Cal-BI": ["calibriz.ttf", "Carlito-BoldItalic.ttf", "C:/Windows/Fonts/calibriz.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf"],
}
_cams = {}
for _nome, _lista in _FONTES.items():
    _cams[_nome] = _1o_existente([os.path.join(_AQUI, "fonts", f) for f in _lista[:2]] + _lista[2:])
_base = _cams["Cal"] or _1o_existente(list(_cams.values()))
# Se nenhuma fonte em arquivo for encontrada (caso do servidor Linux do Streamlit),
# usa a fonte interna Helvetica (embutida no reportlab) sob os mesmos nomes — assim o
# PDF SEMPRE é gerado, nunca dá "no afm found".
_FALLBACK = {"Cal": "Helvetica", "Cal-B": "Helvetica-Bold",
             "Cal-I": "Helvetica-Oblique", "Cal-BI": "Helvetica-BoldOblique"}
for _nome in ("Cal", "Cal-B", "Cal-I", "Cal-BI"):
    _c = _cams[_nome] or _base
    _ok = False
    if _c:
        try:
            pdfmetrics.registerFont(TTFont(_nome, _c))
            _ok = True
        except Exception:
            _ok = False
    if not _ok:
        try:
            pdfmetrics.registerFont(pdfmetrics.Font(_nome, _FALLBACK[_nome], "WinAnsiEncoding"))
        except Exception:
            pass
pdfmetrics.registerFontFamily("Cal", normal="Cal", bold="Cal-B", italic="Cal-I", boldItalic="Cal-BI")

NAVY = colors.HexColor("#1F3864")
BLUE = colors.HexColor("#2F5597")
LABEL = colors.HexColor("#DCE6F1")
NOTE = colors.HexColor("#EEF3F9")
WARN = colors.HexColor("#FCE4D6")
OKC = colors.HexColor("#E2EFDA")
GRID = colors.HexColor("#B4C0D4")

body = ParagraphStyle("body", fontName="Cal", fontSize=10, leading=13.2, alignment=TA_JUSTIFY, spaceAfter=5)
small = ParagraphStyle("small", parent=body, fontSize=8.8, leading=11.2, spaceAfter=3)
cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=11.2, alignment=TA_LEFT, spaceAfter=0)
cellc = ParagraphStyle("cellc", parent=cell, alignment=TA_CENTER)
cellh = ParagraphStyle("cellh", parent=cellc, fontName="Cal-B", textColor=colors.white)
celll = ParagraphStyle("celll", parent=cell, fontName="Cal-B", textColor=NAVY)
h1 = ParagraphStyle("h1", fontName="Cal-B", fontSize=13.5, leading=17, textColor=BLUE, spaceBefore=11, spaceAfter=5, keepWithNext=1)
h2 = ParagraphStyle("h2", fontName="Cal-B", fontSize=11.5, leading=14.5, textColor=BLUE, spaceBefore=8, spaceAfter=4, keepWithNext=1)
h3 = ParagraphStyle("h3", fontName="Cal-B", fontSize=10.3, leading=13, textColor=NAVY, spaceBefore=5, spaceAfter=3, keepWithNext=1)
title = ParagraphStyle("title", fontName="Cal-B", fontSize=17, leading=21, textColor=NAVY, alignment=TA_CENTER)
sub = ParagraphStyle("sub", fontName="Cal", fontSize=10.5, leading=14, alignment=TA_CENTER)
formula = ParagraphStyle("formula", parent=body, alignment=TA_CENTER, fontName="Cal-B", spaceAfter=2)

W = A4[0] - 4 * cm


def P(t, s=body): return Paragraph(t, s)


def box(text, bg=NOTE, border=BLUE):
    t = Table([[Paragraph(text, small)]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 2.5, border),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def kv(rows):
    data = [[P(k, celll), P(v, cell)] for k, v in rows]
    t = Table(data, colWidths=[4.0 * cm, W - 4.0 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), LABEL), ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    return t


def grid(header, rows, widths, shade=None, center_from=1):
    data = [[P(h, cellh) for h in header]]
    for r in rows:
        data.append([P(c, cellc if i >= center_from else cell) for i, c in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.5, GRID),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    for (c, r, color) in (shade or []):
        st.append(("BACKGROUND", (c, r), (c, r), color))
    t.setStyle(TableStyle(st))
    return t


class NumCanvas(canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self.deco(n)
            super().showPage()
        super().save()

    def deco(self, n):
        self.setFont("Cal", 8)
        self.setFillColor(colors.HexColor("#666666"))
        self.drawRightString(A4[0] - 2 * cm, A4[1] - 1.1 * cm,
                             HDR[0])
        self.setStrokeColor(GRID)
        self.line(2 * cm, 1.75 * cm, A4[0] - 2 * cm, 1.75 * cm)
        self.drawCentredString(A4[0] / 2, 1.3 * cm, FOOT[0])
        self.drawCentredString(A4[0] / 2, 0.9 * cm, f"Página {self._pageNumber} de {n}")




def build(emp, sig, f, DATA, outpath, coletar=None):
    n = f["nome"]
    _textos = f.get("textos") or {}

    def tx(k, d):
        """Texto editável: devolve o texto do usuário (f['textos'][k]) ou o padrão; `coletar` recebe os padrões."""
        if coletar is not None:
            coletar[k] = d
        return _textos.get(k) or d

    key = f.get("key", n)
    HDR[0] = f"LTCAT \u2013 {n} | {emp['nome_curto']}"
    FOOT[0] = emp['rodape']
    S = []
    S += []
    if emp.get("logo") and os.path.exists(emp["logo"]):
        from PIL import Image as _PI
        _w, _h = _PI.open(emp["logo"]).size
        logo = Image(emp["logo"], width=4.6 * cm, height=4.6 * cm * _h / _w)
        logo.hAlign = "CENTER"
        S += [logo, Spacer(1, 8)]
    S += [P("LAUDO TÉCNICO DAS CONDIÇÕES AMBIENTAIS DO TRABALHO", title),
          P("L T C A T", ParagraphStyle("t2", parent=title, fontSize=11, leading=16)), Spacer(1, 6),
          P(f"Função avaliada: <font name='Cal-B' color='#2F5597'>{n}</font>", sub),
          P(f"Setor: <b>{f['setor']}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Escopo: <b>Coletivo (GHE {n.capitalize()})</b>", sub),
          P(f"<i>Emitido em: {DATA}</i>", ParagraphStyle("em", parent=sub, fontSize=9.5, textColor=colors.HexColor("#555555"))),
          Spacer(1, 6),
          box(tx("fundamentacao", "<b>Fundamentação legal e normativa</b><br/>Lei nº 8.213/91 (art. 58); Decreto nº 3.048/99 e Anexo IV (agentes nocivos para fins de "
              "aposentadoria especial); Instrução Normativa PRES/INSS nº 128/2022 (arts. 276 e seguintes); NR-01 (GRO/PGR); NR-09 (avaliação e "
              "controle das exposições ocupacionais); NR-15 (Anexos 1 – Ruído, 3 – Calor, 8 – Vibração, 10 – Umidade, 11 e 13 – Agentes Químicos "
              "e 14 – Agentes Biológicos); Norma de Higiene Ocupacional da Fundacentro NHO-06 (calor).")),
          P("1. Identificação da Empresa", h1),
          kv([("Razão Social", emp["razao"]),
              ("Endereço", emp["endereco"]),
              ("CNPJ", emp["cnpj"]),
              ("Atividade / CNAE", emp["cnae"]),
              ("Grau de Risco", emp["grau_risco"]),
              ("Setor / Função", f["ident_setor"]),
              ("Escopo do laudo", f"Coletivo \u2013 aplicável ao Grupo Homogêneo de Exposição (GHE) da função {n.capitalize()}")]),
          P("2. Objetivo", h1),
          P(tx("objetivo", f"Este laudo tem por objetivo caracterizar as condições ambientais de trabalho da função de {n} da empresa acima identificada, "
            f"mediante a avaliação dos agentes {f['agentes_obj']} a que o trabalhador está exposto, subsidiando o preenchimento do Perfil "
            "Profissiográfico Previdenciário (PPP) e a verificação de eventual enquadramento como atividade exercida em condições especiais, "
            "nos termos da Lei nº 8.213/91, do Decreto nº 3.048/99 (Anexo IV) e da IN PRES/INSS nº 128/2022.")),
          P("3. Diligência e Caracterização da Avaliação", h1),
          P(tx("diligencia", f"A inspeção do posto de trabalho e as avaliações deste laudo foram realizadas em {DATA}, pelo " + sig["titulo"] + " "
            + sig["nome"] + ", nas dependências da empresa (" + emp["endereco_curto"] + "), durante a "
            "execução normal das atividades da função, com " + f.get("instrumentos", "dosímetro de ruído") +
            ". As atividades, os processos, as condições ambientais e o <i>layout</i> observados são os habituais da função, o que confere "
            "representatividade aos resultados para o GHE." + (" " + f["quim"].get("coleta_txt", "A avaliação quantitativa dos agentes químicos está descrita no item 8.")
             if f["quim"].get("res") else ""))), Spacer(1, 2),
          P(tx("exposicao", "<b>Exposição:</b> os agentes avaliados são inerentes à execução das atividades da função durante a jornada. A "
            "<i>habitualidade e permanência</i> da exposição são analisadas, para cada agente, nos itens 7 (agentes físicos), 8 (agentes químicos) e 9 (agentes biológicos) e consolidadas na síntese do item 12.")),
          P("4. Metodologia e Instrumentação", h1),
          P(tx("met_ruido", "<b>Ruído:</b> avaliação por dosimetria representativa da jornada de trabalho, com base nos limites de tolerância e critérios da "
            "NR-15, Anexo 1 \u2013 limite de 85 dB(A) para jornada de 8 horas, nível de ação de 80 dB(A) (NR-09) e incremento de duplicação de "
            "dose (q) igual a 5 dB. Resultados expressos em Nível de Exposição Normalizado (NEN/TWA) para 8 horas "
            "e em dose diária (%)."))]
    S += [P(tx("met_calor", "<b>Calor:</b> avaliação qualitativa conforme Anexo 3 da NR-15 e NHO-06 da Fundacentro, considerando as fontes geradoras de calor, "
            "o tipo de atividade e o regime de trabalho no posto, para verificação da necessidade de avaliação quantitativa (IBUTG)."))]
    if f.get("vci_ref"):
        S += [P(tx("met_vci", "<b>Vibração de corpo inteiro (VCI):</b> avaliação conforme NR-09, Anexo 1 e NHO-09 da Fundacentro, pela Aceleração Resultante de "
                "Exposição Normalizada (aren) e pelo Valor da Dose de Vibração Resultante (VDVR), com base em resultado de referência da mesma "
                "frota (item 7.3)."))]
    S += [P(tx("met_quim", ("<b>Agentes químicos:</b> avaliação quantitativa por coleta pessoal na zona respiratória e análise laboratorial (NIOSH/MDHS), comparada aos "
             "limites de exposição ocupacional da NR-15 (Anexos 11 e 12) e da ACGIH (item 8); <b>agentes biológicos:</b> avaliação qualitativa, "
             "com enquadramento no Anexo 14 da NR-15 e no Anexo IV do Decreto nº 3.048/99.") if f["quim"].get("res") else
           "<b>Agentes químicos e biológicos:</b> avaliação qualitativa do posto de trabalho (fonte geradora, via de exposição, frequência/tempo "
            "de exposição e medidas de controle), com enquadramento nos Anexos 10, 11, 12, 13 e 14 da NR-15 e no Anexo IV do Decreto nº 3.048/99.")),
          P("5. Descrição do Ambiente Laborativo", h1)]
    S += [P(t) for t in f["ambiente"]]
    S += [P("6. Descrição das Atividades", h1), P(f["atividades"]),
          P("7. Avaliação dos Agentes Físicos", h1), P("7.1 \u2013 Exposição ao Ruído", h2),
          ]
    r = f["ruido"]
    if r.get("med"):
        d, t, ne = r["med"]
        S += [P(tx("ruido_intro", f"Foi identificado o ciclo de exposição representativo da jornada. Após {t} minutos de medição, obteve-se dose acumulada (D) "
                f"de {d}%, projetada para a jornada padrão de 480 minutos, pela expressão:")),
              P("NE = LC + q × log<sub>2</sub> [ (D × TC) / (100 × T) ]", formula),
              P("equivalente a NE = 85 + 16,61 × log<sub>10</sub> [ (D × TC) / (100 × T) ], onde LC = 85 dB(A); q = 5 dB (16,61 = 5/log<sub>10</sub>2); "
                f"TC = 480 min; D = {d}%; T = {t} min.", ParagraphStyle("fn", parent=small, alignment=TA_CENTER)), Spacer(1, 3),
              grid(["Parâmetro", "Valor"],
                   [[f"Dose acumulada ({t} min de medição)", f"{d}%"],
                    ["Dose projetada para a jornada de 480 min", f"{r['dose']}%"],
                    ["<b>Nível de Exposição projetado para a jornada (NE)</b>", f"<b>{r['nen']} dB(A)</b> ({ne} dB(A))"],
                    ["Limite de tolerância (NR-15, Anexo 1 – 8 horas)", "85 dB(A)"],
                    ["Nível de ação (NR-09)", "80 dB(A)"]],
                   [W - 6.0 * cm, 6.0 * cm]),
              Spacer(1, 3),
              ]
    else:
        S += [P(tx("ruido_intro", "O nível de exposição foi obtido por dosimetria representativa das atividades da função e normalizado para a jornada padrão de "
                "8 horas (480 min), pela expressão:")),
              P("NEN = LC + q × log<sub>2</sub> [ D / 100 ] &nbsp;&nbsp;(com LC = 85 dB(A); q = 5 dB; D = dose diária)", formula),
              P("equivalente a NEN = 85 + 16,61 × log<sub>10</sub>(D/100), sendo 16,61 = 5/log<sub>10</sub>2 (fator de conversão do logaritmo).",
                ParagraphStyle("fn", parent=small, alignment=TA_CENTER)), Spacer(1, 3)]
        cl = "Abaixo do LT; acima do nível de ação" if r["acima"] else "Abaixo do LT e do nível de ação"
        fonte = r["fonte"] + (f"<br/>(histórico: {r['hist']})" if r["hist"] else "")
        S += [grid(["Função", "NEN dB(A)", "Dose 8 h (%)", "LT dB(A)", "Fonte / data", "Classificação"],
                   [[n, r["nen"], r["dose"], "85,0", fonte, cl]],
                   [2.5 * cm, 1.8 * cm, 2.0 * cm, 1.6 * cm, 5.2 * cm, W - 13.1 * cm], shade=[(5, 1, WARN if r["acima"] else OKC)]),
              Spacer(1, 4)]
    extra = (" O NEN supera o nível de ação de 80 dB(A) (NR-09), motivo pelo qual são mantidos o uso de protetor auricular e as ações de "
             "conservação auditiva.") if r["acima"] else ""
    hist = "" if r["hist"] else ""
    S += [P(tx("ruido_concl", f"<b>Conclusão:</b> o NEN de {r['nen']} dB(A) situa-se abaixo do limite de tolerância de 85 dB(A) da NR-15, Anexo 1.{hist} Não há "
            "caracterização de insalubridade por ruído, tampouco exposição apta ao enquadramento para aposentadoria especial (Decreto "
            "nº 3.048/99, Anexo IV, código 2.0.1)." + extra)),
          P("7.2 \u2013 Exposição ao Calor", h2)]
    c = f["calor"]
    if c["rows"]:
        S += [P("As leituras foram realizadas em " + c.get("data_leitura", DATA) + ", no local de execução das atividades, em regime de trabalho contínuo e atividade "
                "classificada como moderada (taxa metabólica do Quadro 3 da NR-15). O IBUTG foi calculado para ambiente sem carga solar: "
                "IBUTG = 0,7 × tbn + 0,3 × tg."),
              grid(["Local", "tbn (°C)", "tg (°C)", "IBUTG (°C)", "Limite (°C)", "Resultado"], c["rows"],
                   [5.0 * cm, 1.8 * cm, 1.8 * cm, 2.2 * cm, 2.0 * cm, W - 12.8 * cm],
                   shade=[(5, i + 1, OKC) for i in range(len(c["rows"]))]), Spacer(1, 3),
              P(f"<b>Nota:</b> adotou-se, de forma conservadora, o limite de 26,7 °C (Quadro 1 do Anexo 3 da NR-15 \u2013 atividade moderada, "
                f"regime contínuo). O maior IBUTG medido ({c['max']} °C) ficou abaixo do limite.", small)]
    S += [P("<b>Observação:</b> " + c["concl"]), P("7.3 \u2013 Vibração", h2)]
    S += [P(t) for t in f["vibracao"]]
    if f["vib_tab"]:
        S += [grid(["Parâmetro", "Nível de Ação", "Limite de Exposição", "Referência"], f["vib_tab"],
                   [3.0 * cm, 3.6 * cm, 4.2 * cm, W - 10.8 * cm]), Spacer(1, 3)]
    S += [P("<b>Conclusão:</b> " + f["vib_concl"]), P("8. Exposição a Agentes Químicos", h1), P(f["quim"]["intro"])]
    q = f["quim"]
    if q.get("res"):
        for cap, hdr, rws in q["res"]:
            S += [KeepTogether([P("<b>" + cap + "</b>", small),
                                grid(hdr, rws, ([W - 9.6 * cm, 3.4 * cm, 3.1 * cm, 3.1 * cm] if len(hdr) == 4 else [W - 8.8 * cm, 3.6 * cm, 5.2 * cm])), Spacer(1, 4)])]
        S += [P("<b>Conclusão:</b> " + q["concl"])]
    elif q["rows"]:
        S += [grid(["Agente / fonte", "Frequência", "Via", "Controle (EPI)"], q["rows"],
                   [W - 9.2 * cm, 2.4 * cm, 2.4 * cm, 4.4 * cm], center_from=1), Spacer(1, 4), P("<b>Conclusão:</b> " + q["concl"])]
    else:
        S += [P(tx("quim_sem", "Não há enquadramento no Anexo IV do Decreto nº 3.048/99 nem insalubridade pela NR-15 (Anexos 10 a 13) para a função."))]
    S += [P("9. Exposição a Agentes Biológicos", h1),
          P(tx("bio", "Não foi verificado contato com os agentes biológicos constantes do Anexo 14 da NR-15, tampouco exposição enquadrável no Anexo IV "
            "do Decreto nº 3.048/99 para a função avaliada.")),
          P("10. Equipamentos de Proteção Coletiva (EPC) e Medidas de Controle", h1), P(f["epc"]),
          P("11. Equipamentos de Proteção Individual (EPI)", h1), P(f["epi"])]
    s = f["sint"]
    S += [P("12. Síntese do Enquadramento Previdenciário", h1),
          KeepTogether([grid(["Função", "Ruído (NEN)", "Calor", "Agentes químicos", "Vibração", "Enquadramento"],
                             [[n] + s + ["Não caracteriza"]],
                             [2.6 * cm, 2.6 * cm, 3.0 * cm, 3.2 * cm, 2.8 * cm, W - 14.2 * cm], shade=[(5, 1, OKC)]), Spacer(1, 3),
                        P(tx("sint_nota", "Agentes biológicos (NR-15, Anexo 14): ausência. Critério de referência: NR-15 e Decreto nº 3.048/99, Anexo IV "
                          "(ruído: código 2.0.1)."), small)]),
          P("13. Conclusão", h1),
          P(tx("conclusao1", f"Com base nas avaliações ambientais consolidadas, conclui-se que os agentes avaliados situam-se abaixo dos limites de tolerância da "
            f"NR-15 ou não ocorrem de forma habitual e permanente, e <b>não caracterizam exposição apta a ensejar o enquadramento da função de "
            f"{n} como atividade exercida em condições especiais</b> (Decreto nº 3.048/99, Anexo IV).")),
          P(tx("conclusao2", f"Assim, para os fins previdenciários a que se destina este laudo, a função de {n} não se enquadra como atividade especial em "
            "razão dos agentes avaliados.")),
          P("14. Encerramento", h1),
          P(tx("encerramento", "Dou por concluído o objetivo proposto, encerrando este Laudo Técnico das Condições Ambientais do Trabalho para que produza os "
            "efeitos legais cabíveis.")), Spacer(1, 20),
          KeepTogether([P(f"{emp['cidade']}, {DATA}", ParagraphStyle("d", parent=sub)), Spacer(1, 34),
                        P("______________________________________", sub), P("<b>" + sig["nome"] + "</b>", sub),
                        P(sig["titulo"], sub), P(sig["crea"], sub)])]
    if coletar is not None:
        return None
    out = outpath
    doc = BaseDocTemplate(out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2.2 * cm,
                          title=f"LTCAT - {n}", author=sig["nome"])
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(2 * cm, 2.2 * cm, W, A4[1] - 4.0 * cm, id="f", leftPadding=0, rightPadding=0,
                                                             topPadding=0, bottomPadding=0)])])
    doc.build(S, canvasmaker=NumCanvas)
    return out
