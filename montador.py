# -*- coding: utf-8 -*-
"""Assistente de montagem: transforma vários documentos de uma função em um rascunho completo de LTCAT.

Fluxo: documentos -> IA (ou leitura local) devolve um JSON "simplificado" -> `para_laudo` converte para o formato do motor
(`engine.build`) fazendo os cálculos (NE, dose projetada) em Python -> `checagens` gera alertas para conferência.
"""
import base64
import copy
import json
import re
import unicodedata

import extractor as ex_
import leitura_local as LL

REGRAS = """Você monta rascunhos de LTCAT (Laudo Técnico das Condições Ambientais do Trabalho) para um engenheiro de segurança do trabalho, a partir de documentos que ele envia (laudos anteriores, avaliações ambientais, planilhas e fotos de medições, descrições de atividades). O engenheiro revisa tudo antes de assinar.

PRINCÍPIOS
1. Use SOMENTE dados que estão nos documentos ou nas instruções do usuário. Nunca invente medições, limites, datas, nomes, modelos de veículos ou equipamentos. Dado ausente: deixe vazio/null e registre em "pendencias".
2. Redija em português técnico formal, terceira pessoa, no padrão dos exemplos. NÃO cite laudos anteriores, empresas de consultoria ou nomes de engenheiros no texto do laudo (a rastreabilidade vai em "origens"). Única exceção: a frase de coleta química ("por laboratório especializado") e a vibração de referência ("avaliação de referência de DD/MM/AAAA").
3. Sempre registre em "origens" de qual documento (nome do arquivo), data do documento e trecho vem cada dado importante (atividades, ambiente, ruído, calor, químicos, vibração).

CRITÉRIOS TÉCNICOS (siga exatamente)
- RUÍDO: critério NR-15 Anexo 1 (limite 85 dB(A) para 8 h, q = 5 dB; nível de ação 80 dB(A) da NR-09). Informe dose_pct e tempo_min quando a medição trouxer dose acumulada e tempo; se só houver o nível (NE/TWA), informe nen_dBA. Não calcule você mesmo: o sistema calcula o NE e a dose projetada para 480 min.
- CALOR: se não há fonte geradora de calor relevante nas atividades/ambiente (forno, caldeira, estufa, solda contínua em ambiente fechado, sol direto etc.) use a observação padrão (sem leituras): "nos ambientes e nas atividades da função não há fontes geradoras de calor que tenham necessidade de avaliação quantitativa (IBUTG). Assim, não há caracterização de insalubridade por calor (NR-15, Anexo 3), tampouco exposição apta ao enquadramento previdenciário." Só inclua "leituras" de IBUTG se o usuário/documento trouxer medições feitas para este laudo. Se houver fonte de calor e não houver IBUTG, deixe a observação padrão e registre pendência.
- VIBRAÇÃO: aplica_vci = true somente se a função conduz veículo durante a jornada. Nesse caso preencha aren, vdvr e data da referência se existirem nos documentos (limites: nível de ação 0,5 m/s² e 9,1 m/s^1,75; limite de exposição 1,1 m/s² e 21,0 m/s^1,75). Caso contrário, o texto padrão é "Na inspeção não foi constatada exposição a vibração de corpo inteiro (Anexo 8 da NR-15 / NR-09, Anexo 1) para a função, cujas atividades são desenvolvidas ..." (complete com o local real da atividade).
- AGENTES QUÍMICOS: situacao = "sem_exposicao" quando a função não manipula/gera agentes químicos e não há avaliação; "qualitativo" quando há contato (óleos, graxas etc.) sem avaliação quantitativa (informe agente/fonte, frequência, via e EPI); "quantitativo" quando há resultados de laboratório para a função (liste cada agente com resultado, unidade e os limites LEO). Use apenas as linhas do setor/função do laudo. Compare cada resultado com o limite da NR-15 (Anexos 11 e 12) quando ele existir; use o TLV da ACGIH apenas como referência quando a NR-15 não tiver limite. Nível de Ação = 50% do limite. Informe leo_acgih e leo_nr15 como no documento (ou "leo_adotado" quando o usuário pedir um único limite). Nunca escreva "Índice de Exposição" no texto.
- Conclusão do item de químicos: se todos os resultados estão abaixo do Nível de Ação, diga que estão abaixo do limite e do Nível de Ação, em situação controlada, e que não há caracterização de insalubridade (NR-15, Anexos 11 e 12) nem exposição apta ao enquadramento previdenciário (Decreto nº 3.048/99, Anexo IV, art. 65 e IN PRES/INSS nº 128/2022). Se algum agente passar do Nível de Ação mas não do limite da NR-15, diga isso explicitamente, recomende controle/monitoramento e reavaliação, e registre pendência. Se passar do limite da NR-15, NÃO conclua "não caracteriza": registre pendência de alta prioridade.
- EPC e EPI: descreva apenas o que consta nos documentos (ventilação natural/mecânica, pé-direito, iluminação, manutenção preventiva; protetor auricular, creme protetor, respirador etc.). Se não constar, use frase neutra e registre pendência. Vibração de corpo inteiro não é controlável por EPI.
- Ambiente: descreva o local de trabalho com as dimensões/características que constarem; não generalize para outro setor.
- recomendacoes: ações recomendadas coerentes com os achados (conservação auditiva se NE ≥ 80; respirador/controle se químicos acima do nível de ação; medidas para VCI acima do nível de ação). Lista vazia se nada se aplica.

FORMATO DE SAÍDA: APENAS um JSON válido (sem texto fora dele) com esta estrutura:
{
 "funcao": {"nome": "", "setor": "", "ident_setor": ""},
 "ambiente": ["parágrafo 1", "parágrafo 2"],
 "atividades": "",
 "ruido": {"dose_pct": "", "tempo_min": "", "nen_dBA": "", "fonte": "Dosimetria"},
 "calor": {"observacao": "", "data_leitura": "", "leituras": [{"local": "", "tbn": "", "tg": "", "ibutg": "", "limite": ""}]},
 "vibracao": {"aplica_vci": false, "texto": "", "aren": "", "vdvr": "", "data_referencia": ""},
 "quimicos": {"situacao": "sem_exposicao|qualitativo|quantitativo", "intro": "", "conclusao": "", "coleta_txt": "",
              "linhas": [{"grupo": "", "agente": "", "resultado": "", "unidade": "", "leo_acgih": "", "leo_nr15": "", "leo_adotado": ""}],
              "qualitativo": [{"agente_fonte": "", "frequencia": "", "via": "", "epi": ""}]},
 "epc": "", "epi": "",
 "recomendacoes": [""],
 "sintese": {"calor": "", "quimicos": "", "vibracao": ""},
 "pendencias": [{"prioridade": "alta|media|baixa", "campo": "", "motivo": ""}],
 "origens": [{"campo": "", "documento": "", "data_documento": "", "trecho": ""}]
}
Textos em HTML simples: use <b>negrito</b> e <super>1,75</super> (expoente) quando necessário. Use vírgula decimal. Para "intro" de quimicos sem exposição use: "Observação: não foi constatada exposição a agentes químicos na função que demande avaliação quantitativa ou caracterize nocividade." Em "sintese": textos curtos para a tabela (ex.: "Sem fonte geradora<br/>de calor", "Ausência", "Não identificada")."""

CALOR_PADRAO = ("nos ambientes e nas atividades da função não há fontes geradoras de calor que tenham necessidade de avaliação "
                "quantitativa (IBUTG). Assim, não há caracterização de insalubridade por calor (NR-15, Anexo 3), tampouco exposição apta ao "
                "enquadramento previdenciário.")
QUIM_SEM = ("Observação: não foi constatada exposição a agentes químicos na função que demande avaliação quantitativa ou caracterize nocividade.")
VIB_SEM = ("Na inspeção não foi constatada exposição a vibração de corpo inteiro (Anexo 8 da NR-15 / NR-09, Anexo 1) para a função.")


# ------------------------------------------------------------------ chamada da IA
def montar_com_ia(docs, empresa_nome, funcao, data_laudo, extras="", cliente=None, modelo=None):
    """docs: lista de dicts {nome, texto (str|''), imagens (list[b64 jpeg])}."""
    if cliente is None:
        import anthropic
        chave = ex_.chave_api()
        if not chave:
            raise RuntimeError("Chave da API não configurada (menu Configurações).")
        cliente = anthropic.Anthropic(api_key=chave)
    blocos = []
    for d in docs:
        cab = f"<documento nome=\"{d['nome']}\">"
        if d.get("texto"):
            blocos.append({"type": "text", "text": cab + "\n" + d["texto"][:300000] + "\n</documento>"})
        else:
            blocos.append({"type": "text", "text": cab + " (imagens das páginas a seguir)"})
        for b in d.get("imagens") or []:
            blocos.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}})
        if not d.get("texto"):
            blocos.append({"type": "text", "text": "</documento>"})
    pedido = (f"Monte o rascunho do LTCAT.\nEmpresa: {empresa_nome}\nFunção: {funcao}\nData do laudo: {data_laudo}\n"
              + (f"Instruções do engenheiro: {extras}\n" if extras.strip() else "")
              + "Use os documentos acima. Devolva somente o JSON no formato definido.")
    blocos.append({"type": "text", "text": pedido})
    resp = cliente.messages.create(model=modelo or ex_.carregar_config().get("modelo") or ex_.MODELO_PADRAO, max_tokens=16000,
                                   system=REGRAS, messages=[{"role": "user", "content": blocos}])
    txt = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return ex_._json_da_resposta(txt)


# ------------------------------------------------------------------ montagem sem IA
def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def montar_sem_ia(docs, funcao, data_laudo):
    """Combina a leitura local de vários documentos em um JSON simplificado (mesmo formato da IA)."""
    f_nome = funcao.strip()
    radical = _norm(f_nome)[:4]
    simp = {"funcao": {"nome": f_nome, "setor": "", "ident_setor": ""}, "ambiente": [], "atividades": "",
            "ruido": {}, "calor": {"observacao": CALOR_PADRAO, "leituras": []}, "vibracao": {"aplica_vci": False, "texto": VIB_SEM},
            "quimicos": {"situacao": "sem_exposicao", "intro": QUIM_SEM, "linhas": []}, "epc": "", "epi": "", "recomendacoes": [],
            "sintese": {}, "pendencias": [], "origens": []}
    for d in docs:
        lido = LL.leitura_local(d.get("texto", ""), d.get("bytes") if d["nome"].lower().endswith(".pdf") else None, d["nome"])
        dt = lido["documento"].get("data", "")
        for fu in lido["funcoes"]:
            if radical in _norm(fu["nome"]):
                simp["funcao"]["setor"] = simp["funcao"]["setor"] or fu["setor"]
                if fu["atividades"] and not simp["atividades"]:
                    simp["atividades"] = fu["atividades"]
                    simp["origens"].append({"campo": "atividades", "documento": d["nome"], "data_documento": dt, "trecho": fu["atividades"][:120]})
                if fu["ambiente"] and not simp["ambiente"]:
                    simp["ambiente"] = [fu["ambiente"]]
                    simp["origens"].append({"campo": "ambiente", "documento": d["nome"], "data_documento": dt, "trecho": fu["ambiente"][:120]})
        for r in lido["ruido"]:
            if radical in _norm(r.get("funcao", "")) and not simp["ruido"]:
                simp["ruido"] = {"dose_pct": r.get("dose_pct", ""), "tempo_min": r.get("tempo_medicao_min", ""), "nen_dBA": r.get("nen_dBA", ""), "fonte": "Dosimetria"}
                simp["origens"].append({"campo": "ruído", "documento": d["nome"], "data_documento": dt, "trecho": r.get("trecho", "")})
        for v in lido["vibracao"]:
            if radical in _norm(v.get("funcao", "")):
                simp["vibracao"] = {"aplica_vci": True, "aren": v["aren"], "vdvr": v["vdvr"], "data_referencia": v.get("data", ""), "texto": ""}
                simp["origens"].append({"campo": "vibração", "documento": d["nome"], "data_documento": v.get("data", "") or dt, "trecho": v.get("trecho", "")})
        qs = [q for q in lido["quimicos"] if radical in _norm(str(q.get("setor_funcao", "")) + " " + str(q.get("grupo", "")))]
        if qs:
            simp["quimicos"]["situacao"] = "quantitativo"
            simp["quimicos"]["linhas"] += [{k: q.get(k, "") for k in ("grupo", "agente", "resultado", "unidade", "leo_acgih", "leo_nr15")} for q in qs]
            simp["quimicos"]["coleta_txt"] = (f"A avaliação quantitativa dos agentes químicos foi realizada em {qs[0].get('periodo') and dt or dt}, por laboratório "
                                              "especializado, conforme descrito no item 8.")
            simp["quimicos"]["intro"] = ("A avaliação quantitativa foi realizada durante a execução das atividades da função, com coleta pessoal na zona respiratória do "
                                         "trabalhador e análise laboratorial, e os resultados foram comparados aos limites de exposição ocupacional (LEO) da NR-15 e da ACGIH. "
                                         "O Nível de Ação corresponde a 50% do limite de exposição.")
            simp["origens"].append({"campo": "agentes químicos", "documento": d["nome"], "data_documento": dt, "trecho": "; ".join(sorted({q["grupo"] for q in qs}))[:150]})
    p = simp["pendencias"]
    p.append({"prioridade": "media", "campo": "EPC/EPI", "motivo": "A leitura local não redige EPC/EPI; complete os itens 10 e 11 do laudo."})
    if simp["quimicos"]["situacao"] == "quantitativo":
        simp["quimicos"]["conclusao"] = ""
        p.append({"prioridade": "alta", "campo": "químicos", "motivo": "Redija a conclusão do item 8 após conferir as linhas (a leitura local não conclui)."})
    return simp


# ------------------------------------------------------------------ conversão para o formato do motor
def base_laudo(empresa_id):
    return {"id": "", "key": "", "nome": "", "setor": "", "ident_setor": "", "empresa_id": empresa_id, "data_laudo": "",
            "instrumentos": "dosímetro de ruído", "vci_ref": False, "ambiente": [], "atividades": "",
            "agentes_obj": "físicos (ruído e calor), químicos e biológicos",
            "ruido": {"nen": "", "dose": "", "fonte": "Dosimetria", "hist": None, "acima": False},
            "calor": {"rows": None, "max": None, "data_leitura": "", "concl": CALOR_PADRAO},
            "vibracao": [VIB_SEM], "vib_tab": None, "vib_concl": "não há agente vibração a caracterizar para a função.",
            "quim": {"rows": None, "intro": QUIM_SEM, "concl": None}, "epc": "", "epi": "",
            "sint": ["", "Sem fonte geradora<br/>de calor", "Ausência", "Não identificada"], "rec": []}


def _s(x):
    return "" if x is None else str(x).strip()


def para_laudo(simp, empresa_id, funcao, data_laudo, slug_fn):
    f = base_laudo(empresa_id)
    fu = simp.get("funcao") or {}
    f["nome"] = (_s(fu.get("nome")) or funcao).upper()
    f["setor"] = _s(fu.get("setor"))
    f["ident_setor"] = _s(fu.get("ident_setor")) or (f["setor"] + " / " + f["nome"].capitalize()).strip(" /")
    f["data_laudo"] = data_laudo
    f["ambiente"] = [_s(a) for a in (simp.get("ambiente") or []) if _s(a)]
    f["atividades"] = _s(simp.get("atividades"))
    # ruído
    ru = simp.get("ruido") or {}
    if _s(ru.get("dose_pct")) or _s(ru.get("nen_dBA")):
        ex_.aplicar_ruido(f, {"nen_dBA": ru.get("nen_dBA"), "dose_pct": ru.get("dose_pct"), "tempo_medicao_min": ru.get("tempo_min")})
        if _s(ru.get("fonte")):
            f["ruido"]["fonte"] = _s(ru["fonte"])
    # calor
    ca = simp.get("calor") or {}
    f["calor"]["concl"] = _s(ca.get("observacao")) or CALOR_PADRAO
    lei = [l for l in (ca.get("leituras") or []) if _s(l.get("ibutg")) or _s(l.get("tbn"))]
    if lei:
        ex_.aplicar_calor(f, lei, _s(ca.get("data_leitura")))
    # vibração
    vi = simp.get("vibracao") or {}
    if vi.get("aplica_vci"):
        f["agentes_obj"] = "físicos (ruído, calor e vibração de corpo inteiro), químicos e biológicos"
        f["vci_ref"] = True
        if _s(vi.get("aren")) and _s(vi.get("vdvr")):
            LL.aplicar_vibracao(f, {"aren": vi["aren"], "vdvr": vi["vdvr"], "data": _s(vi.get("data_referencia"))})
        elif _s(vi.get("texto")):
            f["vibracao"] = [_s(vi["texto"])]
    elif _s(vi.get("texto")):
        f["vibracao"] = [_s(vi["texto"])]
    # químicos
    qu = simp.get("quimicos") or {}
    sit = _s(qu.get("situacao")) or "sem_exposicao"
    if sit == "quantitativo" and qu.get("linhas"):
        grupos = {}
        for l in qu["linhas"]:
            if _s(l.get("agente")):
                grupos.setdefault((_s(l.get("grupo")) or "Resultados", _s(l.get("unidade"))), []).append(l)
        res = []
        for (cap, un), rs in grupos.items():
            if any(_s(x.get("leo_adotado")) for x in rs):
                res.append([cap, ["Agente químico", f"Resultado ({un})", f"LEO adotado ({un})"],
                            [[_s(x["agente"]), _s(x.get("resultado")), _s(x.get("leo_adotado")) or "–"] for x in rs]])
            else:
                res.append([cap, ["Agente químico", f"Resultado ({un})", f"LEO ACGIH ({un})", f"LEO NR-15 ({un})"],
                            [[_s(x["agente"]), _s(x.get("resultado")), _s(x.get("leo_acgih")) or "–", _s(x.get("leo_nr15")) or "–"] for x in rs]])
        f["quim"] = {"rows": None, "res": res, "intro": _s(qu.get("intro")), "concl": _s(qu.get("conclusao")),
                     "coleta_txt": _s(qu.get("coleta_txt")) or "A avaliação quantitativa dos agentes químicos está descrita no item 8."}
    elif sit == "qualitativo" and qu.get("qualitativo"):
        f["quim"] = {"rows": [[_s(x.get("agente_fonte")), _s(x.get("frequencia")), _s(x.get("via")), _s(x.get("epi"))] for x in qu["qualitativo"]],
                     "intro": _s(qu.get("intro")), "concl": _s(qu.get("conclusao"))}
    else:
        f["quim"] = {"rows": None, "intro": _s(qu.get("intro")) or QUIM_SEM, "concl": None}
    f["epc"] = _s(simp.get("epc"))
    f["epi"] = _s(simp.get("epi")) or ("Para os agentes avaliados, cujos resultados situam-se abaixo dos respectivos limites de tolerância, "
                                      "não há EPI obrigatório para neutralização de nocividade.")
    f["rec"] = [_s(r) for r in (simp.get("recomendacoes") or []) if _s(r)]
    si = simp.get("sintese") or {}
    s = f["sint"]
    if f["ruido"].get("nen"):
        s[0] = f"{f['ruido']['nen']} dB(A)<br/>(LT 85)"
    s[1] = _s(si.get("calor")) or s[1]
    s[2] = _s(si.get("quimicos")) or s[2]
    s[3] = _s(si.get("vibracao")) or s[3]
    f["sint"] = s
    f["origens"] = [{"campo": _s(o.get("campo")), "documento": _s(o.get("documento")), "data_documento": _s(o.get("data_documento")),
                     "responsavel": "", "trecho": _s(o.get("trecho"))[:200]} for o in (simp.get("origens") or [])]
    f["id"] = slug_fn(f["nome"]).lower()
    f["key"] = slug_fn(f["nome"])
    alertas = [("alta" if p.get("prioridade") == "alta" else "media" if p.get("prioridade") == "media" else "baixa",
                f"{_s(p.get('campo'))}: {_s(p.get('motivo'))}") for p in (simp.get("pendencias") or [])]
    return f, alertas + checagens(f)


# ------------------------------------------------------------------ verificações automáticas
def _num(s):
    s = _s(s)
    if s.startswith("<") or s in ("", "–", "-", "---"):
        return None
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None


def checagens(f):
    out = []
    r = f.get("ruido", {})
    if not r.get("nen"):
        out.append(("alta", "ruído: não informado. O laudo não pode ser emitido sem a medição."))
    else:
        v = _num(r["nen"])
        if v is not None and v > 85:
            out.append(("alta", f"ruído: NE {r['nen']} dB(A) ACIMA do limite de 85 dB(A) — o texto automático \"abaixo do limite\" não vale; revise conclusões."))
        elif v is not None and v >= 80.05:
            out.append(("media", f"ruído: NE {r['nen']} dB(A) acima do nível de ação (80): o laudo inclui conservação auditiva/protetor auricular."))
        if not r.get("med"):
            out.append(("media", "ruído: sem dose e tempo de medição — o NE foi usado como informado; confirme a normalização para 8 h."))
    q = f.get("quim", {})
    for cap, hdr, rows in (q.get("res") or []):
        for rw in rows:
            res = _num(rw[1])
            lim_nr = _num(rw[3]) if len(rw) > 3 else None
            lim_ac = _num(rw[2]) if len(rw) > 3 else _num(rw[2])
            lim = lim_nr if lim_nr is not None else lim_ac
            if res is not None and lim:
                ie = res / lim
                if ie > 1:
                    out.append(("alta", f"químicos: {rw[0]} ({cap}) = {rw[1]} ACIMA do limite adotado ({fmt_lim(lim)}) — não conclua \"não caracteriza\" sem revisar."))
                elif ie > 0.5:
                    out.append(("media", f"químicos: {rw[0]} ({cap}) = {rw[1]} acima do Nível de Ação (50% de {fmt_lim(lim)}): medidas de controle e reavaliação."))
            if res is not None and lim_nr is not None and lim_ac is not None and res > lim_ac >= 0 and res <= lim_nr and len(rw) > 3:
                out.append(("baixa", f"informativo: {rw[0]} ({cap}) acima do TLV da ACGIH ({fmt_lim(lim_ac)}) e abaixo do limite da NR-15 ({fmt_lim(lim_nr)})."))
    if q.get("res") and not q.get("concl"):
        out.append(("alta", "químicos: a conclusão do item 8 está vazia."))
    if not f.get("atividades"):
        out.append(("alta", "atividades: descrição vazia."))
    if not f.get("ambiente"):
        out.append(("media", "ambiente: descrição vazia."))
    if not f.get("epc"):
        out.append(("baixa", "EPC: texto vazio (item 10)."))
    ano_l = ex_.ano(f.get("data_laudo"))
    docs_antigos = sorted({o["documento"] + " (" + (o.get("data_documento") or "s/data") + ")" for o in f.get("origens", [])
                           if ex_.ano(o.get("data_documento")) and ano_l and ex_.ano(o.get("data_documento")) != ano_l})
    if docs_antigos:
        out.append(("media", "datas: dados de documentos de ano diferente do laudo: " + "; ".join(docs_antigos) + ". Confirme se foram remedidos."))
    v = f.get("vib_concl", "")
    if "ULTRAPASSAM" in v:
        out.append(("alta", "vibração: valores acima do limite de exposição — há insalubridade por VCI; revise conclusões."))
    return out


def fmt_lim(x):
    return f"{x:g}".replace(".", ",")
