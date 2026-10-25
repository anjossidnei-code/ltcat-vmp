# -*- coding: utf-8 -*-
"""Leitura local (sem IA, sem internet) de laudos e avaliações nos formatos usados pela empresa.

Reconhece:
  * LTCAT no formato City/STU ("FUNÇÃO:", "SETOR:", descrição, ruído, AREN/VDVR);
  * avaliações de agentes químicos em tabelas (relatórios de ensaio, formato Toximaster).
Devolve a mesma estrutura da extração por IA, para passar pela tela de conferência.
"""
import re

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _limpa(t):
    t = re.sub(r"[ \t]+", " ", t or "")
    t = re.sub(r"\n\s*\d+\s*\n", "\n", t)          # números de página soltos
    t = re.sub(r"\s*\n\s*", " ", t)
    return t.strip()


def _data_documento(txt):
    ms = list(re.finditer(r"(\d{1,2}) de (" + "|".join(MESES) + r") de (\d{4})", txt, re.I))
    if ms:
        m = ms[-1]
        return f"{int(m.group(1)):02d}/{MESES.index(m.group(2).lower()) + 1:02d}/{m.group(3)}"
    m = re.search(r"Data\s*[:\s]\s*(\d{2}/\d{2}/\d{4})", txt)
    if m:
        return m.group(1)
    m = re.search(r"(" + "|".join(MESES) + r")\s*[-–]\s*(\d{4})", txt, re.I)
    if m:
        return f"{MESES.index(m.group(1).lower()) + 1:02d}/{m.group(2)}"
    return ""


def _docs_base():
    return {"documento": {}, "funcoes": [], "ruido": [], "calor": [], "quimicos": [], "vibracao": [], "epi": []}


def _ler_ltcat_texto(texto, saida):
    """Formato City/STU (texto corrido)."""
    partes = re.split(r"(?=FUN[ÇC][ÃA]O:\s)", texto)
    for blk in partes:
        m = re.match(r"FUN[ÇC][ÃA]O:\s*([^\n]+)", blk)
        if not m:
            continue
        nome = m.group(1).strip().title()
        setor = re.search(r"SETOR:\s*([^\n]+)", blk)
        amb = re.search(r"Descri[çc][ãa]o do local/posto de trabalho:\s*(.*?)\s*Descri[çc][ãa]o das atividades", blk, re.S)
        ati = re.search(r"Descri[çc][ãa]o das atividades:\s*(.*?)\s*Agentes nocivos", blk, re.S)
        jor = re.search(r"jornada de trabalho:\s*([\d.,]+)\s*h", blk)
        saida["funcoes"].append({"nome": nome, "setor": setor.group(1).strip().title() if setor else "",
                                 "atividades": _limpa(ati.group(1)) if ati else "", "ambiente": _limpa(amb.group(1)) if amb else ""})
        for r in re.finditer(r"ru[ií]do de ([\d.,]+) dB\(A\)", blk):
            saida["ruido"].append({"funcao": nome, "nen_dBA": r.group(1).replace(".", ","), "dose_pct": "", "tempo_medicao_min": "",
                                   "limite_dBA": "", "trecho": _limpa(blk[max(0, r.start() - 60):r.end() + 60])[:160]
                                   + (f" (jornada {jor.group(1)} h)" if jor else "")})
        v = re.search(r"AREN\s*=\s*([\d.,]+)\s*m/s.*?VDVR\s*=\s*([\d.,]+)", blk, re.S | re.I)
        if v:
            dv = re.search(r"realizado em (\d{2}/\d{2}/\d{4})", blk)
            saida["vibracao"].append({"funcao": nome, "aren": v.group(1).replace(".", ","), "vdvr": v.group(2).replace(".", ","),
                                      "data": dv.group(1) if dv else "", "trecho": _limpa(blk[max(0, v.start() - 40):v.end()])[:160]})


def _ler_tabelas_quimicas(pdf_bytes, saida):
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    datas = []
    try:
        for pg in doc:
            tx = pg.get_text()
            if "LEO e Índice de Exposição" not in tx:
                continue
            titulo = re.search(r"Tabela\s*\d+\s*[-–]\s*([^\n]+?)\s*[-–]\s*([^\n]+)", tx)
            setor_nome = titulo.group(1).strip() if titulo else ""
            grupo = f"{setor_nome} - {titulo.group(2).strip()}" if titulo else "Resultados"
            ati = re.search(r"Atividade:\s*(.*?)(?:\n\s*Amostras?:|\n\s*Registro)", tx, re.S)
            per = re.search(r"Per[ií]odo:\s*([\d:]+\s*às\s*[\d:]+)", tx)
            dat = re.search(r"Data\s+(\d{2}/\d{2}/\d{4})", tx)
            try:
                tabs = pg.find_tables().tables
            except Exception:
                tabs = []
            for tb in tabs:
                rows = tb.extract()
                if not rows or not any("Agente" in (c or "") for c in rows[0]):
                    continue
                unidade = ""
                for r in rows[:3]:
                    for c in r:
                        u = re.search(r"(mg/m³|ppm|µg/m³|mg/m3)", c or "")
                        if u:
                            unidade = u.group(1)
                for r in rows:
                    c = [(x or "").replace("\n", " ").strip() for x in r]
                    if len(c) < 7 or not c[0] or c[0].startswith(("Agente", "Conclus", "Índice", "Observ")):
                        continue
                    if not re.search(r"\d", c[1]):
                        continue
                    nome_ag = re.sub(r"(\w)- (\w)", r"\1\2", c[0])
                    saida["quimicos"].append({
                        "setor_funcao": setor_nome, "grupo": grupo, "agente": re.sub(r"\s*[IT]$", "", nome_ag) if re.search(r"[a-zê]{3}[IT]$", nome_ag) else nome_ag,
                        "resultado": c[1], "unidade": unidade, "leo_acgih": c[2], "leo_nr15": c[4] if c[4] not in ("---", "") else "",
                        "atividade": _limpa(ati.group(1)) if ati else "", "periodo": per.group(1) if per else "",
                        "trecho": f"{c[0]}: {c[1]} {unidade}"})
            if dat:
                datas.append(dat.group(1))
        if datas:
            saida["documento"]["data"] = sorted(datas, key=lambda s: s[6:] + s[3:5] + s[:2])[0]
    finally:
        doc.close()


def leitura_local(texto, pdf_bytes=None, nome_arquivo=""):
    """Lê o documento sem IA. `texto` é o texto extraído; `pdf_bytes` permite ler tabelas de PDFs."""
    saida = _docs_base()
    d = saida["documento"]
    d["data"] = _data_documento(texto)
    emp = re.search(r"DADOS DA EMPRESA\s*\n+((?:[^\n]*\n){1,8})", texto)
    if emp:
        for linha in emp.group(1).split("\n"):
            if re.search(r"\b(LTDA|S/A|S\.A\.?|EIRELI|ME|EPP)\b", linha, re.I):
                d["empresa"] = linha.strip()
                break
    resp = re.search(r"\n\s*([A-ZÀ-Ú][^\n]{4,50})\n\s*Eng[^\n]*\n(?:\s*\n)*\s*(?:Respons[^\n]*\n\s*)?CREA", texto)
    if resp:
        d["responsavel_tecnico"] = resp.group(1).strip().title()
    d["tipo"] = "LTCAT" if re.search(r"LTCAT|CONDI[ÇC][ÕO]ES DO AMBIENTE DE TRABALHO", texto, re.I) else ""
    _ler_ltcat_texto(texto, saida)
    if pdf_bytes:
        antes = len(saida["quimicos"])
        try:
            _ler_tabelas_quimicas(pdf_bytes, saida)
        except Exception:
            pass
        if len(saida["quimicos"]) > antes:
            d["tipo"] = "Avaliação ambiental de agentes químicos"
            if not d.get("empresa"):
                m = re.search(r"Cliente\s+([^\n]+)", texto)
                if m:
                    d["empresa"] = m.group(1).strip()
    return saida


# ---------------------------------------------------------------- aplicação da vibração
def _n(s):
    try:
        return float(str(s).replace(",", "."))
    except Exception:
        return None


def aplicar_vibracao(f, item):
    """Monta o texto, a tabela de referência e a conclusão de VCI a partir de aren/VDVR lidos."""
    aren, vdvr = _n(item.get("aren")), _n(item.get("vdvr"))
    if aren is None or vdvr is None:
        return None
    data = item.get("data") or "data não informada"
    acima_na = aren > 0.5 or vdvr > 9.1
    acima_le = aren > 1.1 or vdvr > 21.0
    sup = "<super>1,75</super>"
    f["vibracao"] = [("A função conduz o ônibus durante a jornada. Foi adotada como referência a avaliação quantitativa de vibração de corpo inteiro (VCI) "
                      f"realizada em ônibus da mesma frota ({data}), que obteve aren = {item['aren']} m/s² e VDVR = {item['vdvr']} m/s{sup}, "
                      "comparados ao nível de ação (aren 0,5 m/s² / VDVR 9,1 m/s" + sup + ") e ao limite de exposição (aren 1,1 m/s² / VDVR 21,0 m/s"
                      + sup + ") da NR-09/NR-15, por tratar-se do mesmo posto de condução, tipo de veículo e condições de operação.")]
    f["vib_tab"] = [["aren", "0,5 m/s²", "1,1 m/s²", f"{item['aren']} m/s²"],
                    ["VDVR", f"9,1 m/s{sup}", f"21,0 m/s{sup}", f"{item['vdvr']} m/s{sup}"]]
    f["vci_ref"] = True
    if acima_le:
        f["vib_concl"] = ("os valores de referência ULTRAPASSAM o limite de exposição ocupacional; há caracterização de insalubridade por VCI "
                          "(NR-15, Anexo 8). Revise as conclusões do laudo.")
    else:
        f["vib_concl"] = (f"os valores de referência não ultrapassam o limite de exposição ocupacional (aren 1,1 m/s² / VDVR 21,0 m/s{sup}), de modo que não se "
                          "caracteriza insalubridade por VCI (NR-15, Anexo 8) nem exposição apta ao enquadramento previdenciário."
                          + (" Por situarem-se acima do nível de ação (NR-09, Anexo 1), devem ser adotadas medidas preventivas."
                             if acima_na else ""))
    s = list(f.get("sint") or ["", "", "", ""])
    s[3] = "VCI abaixo do LT" + ("; acima do nível de ação (referência)" if acima_na else " (referência)")
    f["sint"] = s
    if acima_na:
        rec = f.setdefault("rec", [])
        txt = ("adotar medidas preventivas para a vibração de corpo inteiro, acima do nível de ação, como (regulagem e manutenção do banco, "
               "manutenção da suspensão e do piso dos veículos, orientação de condução e pausas)")
        if txt not in rec:
            rec.append(txt)
    return f"Vibração: aren {item['aren']} / VDVR {item['vdvr']}" + (" (ACIMA do limite!)" if acima_le else "")
