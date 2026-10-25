# -*- coding: utf-8 -*-
"""Sistema LTCAT - programa local para elaborar laudos (Fase 1 + leitura de documentos)."""
import copy
import glob
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import date

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
import engine  # noqa: E402
import extractor as ex_  # noqa: E402
import leitura_local as LL  # noqa: E402
import montador as MT  # noqa: E402
import store  # noqa: E402  (camada de dados: Supabase na nuvem ou arquivos locais)

D_OUT = os.path.join(tempfile.gettempdir(), "ltcat_saida")  # PDFs gerados sob demanda
os.makedirs(D_OUT, exist_ok=True)
# Sem chave da Anthropic configurada os recursos de IA ficam ocultos (publicacao sem IA).
IA_ATIVA = bool(ex_.chave_api())

st.set_page_config(page_title="Sistema LTCAT", page_icon="📄", layout="wide")

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ------------------------------------------------------------------ utilidades
def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def jsave(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)


def fmt(x, n):
    return f"{x:.{n}f}".replace(".", ",")


def num(s):
    try:
        return float(str(s).replace(",", ".").replace("<", "").strip())
    except Exception:
        return None


def data_extenso(d: date):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def parse_data(txt):
    m = re.match(r"(\d{1,2}) de (\w+) de (\d{4})", txt or "")
    if m and m.group(2) in MESES:
        return date(int(m.group(3)), MESES.index(m.group(2)) + 1, int(m.group(1)))
    return date.today()


def empresas():
    return store.listar("empresa")


def laudos():
    return store.listar("laudo")


def slug(s):
    s = re.sub(r"[^A-Za-z0-9]+", "_", s.upper().replace("Ç", "C").replace("Ã", "A").replace("Á", "A").replace("Â", "A")
               .replace("É", "E").replace("Ê", "E").replace("Í", "I").replace("Ó", "O").replace("Ô", "O").replace("Ú", "U"))
    return s.strip("_")


def novo_laudo(empresa_id):
    return {
        "id": "", "key": "", "nome": "", "setor": "", "ident_setor": "", "empresa_id": empresa_id,
        "data_laudo": data_extenso(date.today()), "instrumentos": "dosímetro de ruído", "vci_ref": False,
        "ambiente": [""], "atividades": "", "agentes_obj": "físicos (ruído e calor), químicos e biológicos",
        "ruido": {"nen": "", "dose": "", "fonte": "Dosimetria", "hist": None, "acima": False},
        "calor": {"rows": None, "max": None, "data_leitura": "",
                  "concl": "nos ambientes e nas atividades da função não há fontes geradoras de calor que tenham necessidade de avaliação "
                           "quantitativa (IBUTG). Assim, não há caracterização de insalubridade por calor (NR-15, Anexo 3), tampouco exposição "
                           "apta ao enquadramento previdenciário."},
        "vibracao": ["Na inspeção não foi constatada exposição a vibração de corpo inteiro (Anexo 8 da NR-15 / NR-09, Anexo 1) para a função."],
        "vib_tab": None, "vib_concl": "não há agente vibração a caracterizar para a função.",
        "quim": {"rows": None, "intro": "Observação: não foi constatada exposição a agentes químicos na função que demande avaliação "
                                        "quantitativa ou caracterize nocividade.", "concl": None},
        "epc": "", "epi": "Para os agentes avaliados, cujos resultados situam-se abaixo dos respectivos limites de tolerância, não há EPI "
                          "obrigatório para neutralização de nocividade.",
        "sint": ["", "Sem fonte geradora<br/>de calor", "Ausência", "Não identificada"], "rec": [],
    }


def calcula_ruido(D, T):
    """Dose D(%) em T(min) -> dose projetada 480 min e NE (fórmula da NR-15, q=5)."""
    proj = D * 480 / T
    ne = 85 + 16.61 * math.log10(D * 480 / (100 * T))
    return proj, ne


# ------------------------------------------------------------------ navegação
if "pagina" not in st.session_state:
    st.session_state.pagina = "Laudos"


def ir_editar(i, gerar=False, novo_emp=None):
    st.session_state.sel = i
    st.session_state.pagina = "Editar laudo"
    if gerar:
        st.session_state.auto_gerar = True
    if novo_emp:
        st.session_state.novo_emp = novo_emp


pagina = st.sidebar.radio("Menu", ["Laudos", "Montar laudo", "Editar laudo", "Empresas", "Signatário", "Ler documentos", "Configurações"], key="pagina")
st.sidebar.caption("Sistema LTCAT · uso local")

if "sel" not in st.session_state:
    st.session_state.sel = None
if "msg" not in st.session_state:
    st.session_state.msg = None

# ================================================================== LAUDOS
if pagina == "Laudos":
    st.title("Laudos")
    L, E = laudos(), empresas()
    c1, c2 = st.columns([3, 1])
    with c2:
        if E:
            st.button("➕ Novo laudo", width='stretch', on_click=ir_editar, args=("__novo__", False, list(E)[0]))
        else:
            st.error("Cadastre uma empresa primeiro.")
    if not L:
        st.info("Nenhum laudo cadastrado.")
    else:
        df = pd.DataFrame([{"Função": l["nome"], "Setor": l["setor"], "Empresa": E.get(l["empresa_id"], {}).get("nome_curto", "?"),
                            "Data": l["data_laudo"], "ID": l["id"]} for l in L.values()])
        st.caption("Clique em uma linha para selecionar o laudo e use os botões abaixo.")
        ev = st.dataframe(df, width='stretch', hide_index=True, on_select="rerun", selection_mode="single-row", key="tab_laudos")
        linhas_sel = ev.selection.rows if ev is not None and getattr(ev, "selection", None) else []
        ids = list(L)
        if linhas_sel:
            escolha = df.iloc[linhas_sel[0]]["ID"]
            st.success(f"Selecionado: **{L[escolha]['nome']}** ({L[escolha]['data_laudo']}) — arquivo `{escolha}`")
        else:
            escolha = st.selectbox("Ou escolha aqui", ids, format_func=lambda i: f"{L[i]['nome']} — {L[i]['data_laudo']} ({i})")
        b1, b2, b3, b4 = st.columns(4)
        b1.button("✏️ Editar", width='stretch', on_click=ir_editar, args=(escolha,))
        b2.button("📄 Gerar PDF", width='stretch', on_click=ir_editar, args=(escolha, True))
        if b3.button("📋 Duplicar", width='stretch'):
            c = copy.deepcopy(L[escolha])
            c["id"] = f"{escolha}_copia"
            c["nome"] = L[escolha]["nome"] + " (cópia)"
            store.salvar("laudo", c["id"], c)
            st.session_state.msg = "Laudo duplicado."
            st.rerun()
        if b4.button("🗑️ Excluir", width='stretch'):
            st.session_state.confirma_excluir = escolha
        if st.session_state.get("confirma_excluir") == escolha:
            st.warning(f"Excluir o laudo de {L[escolha]['nome']}? Esta ação não pode ser desfeita.")
            if st.button("Confirmar exclusão"):
                store.excluir("laudo", escolha)
                st.session_state.confirma_excluir = None
                st.rerun()
    if st.session_state.msg:
        st.success(st.session_state.msg)
        st.session_state.msg = None

# ================================================================== EDITAR
elif pagina == "Editar laudo":
    st.title("Editar laudo")
    L, E = laudos(), empresas()
    sel = st.session_state.sel
    if sel is None:
        sel = st.selectbox("Laudo", list(L), format_func=lambda i: L[i]["nome"]) if L else None
        if sel is None:
            st.info("Escolha ou crie um laudo no menu Laudos.")
            st.stop()
    novo = sel == "__novo__"
    f = novo_laudo(st.session_state.get("novo_emp", list(E)[0])) if novo else copy.deepcopy(L[sel])
    st.caption("Novo laudo" if novo else f"ID: {f['id']}")
    if f.get("origens"):
        ano_laudo = ex_.ano(f.get("data_laudo"))
        with st.expander(f"📎 Origem dos dados importados ({len(f['origens'])})", expanded=False):
            st.dataframe(pd.DataFrame(f["origens"]), width='stretch', hide_index=True)
        antigos = sorted({o["documento"] + " (" + (o.get("data_documento") or "s/data") + ")" for o in f["origens"]
                          if ex_.ano(o.get("data_documento")) and ano_laudo and ex_.ano(o.get("data_documento")) != ano_laudo})
        if antigos:
            st.warning("Há dados importados de documentos de data diferente da data do laudo: " + "; ".join(antigos) +
                       ". Confirme se foram remedidos ou cite a origem no texto antes de emitir.")

    tabs = st.tabs(["Identificação", "Ambiente e atividades", "Ruído", "Calor", "Vibração", "Agentes químicos", "Medidas e síntese", "Textos do laudo"])

    # ---- Identificação
    with tabs[0]:
        c1, c2 = st.columns(2)
        f["nome"] = c1.text_input("Função (como aparece no laudo)", f["nome"]).upper()
        f["setor"] = c2.text_input("Setor (capa)", f["setor"])
        f["ident_setor"] = c1.text_input("Setor / Função (quadro de identificação)", f["ident_setor"] or (f["setor"] + " / " + f["nome"].capitalize()))
        f["empresa_id"] = c2.selectbox("Empresa", list(E), index=list(E).index(f["empresa_id"]) if f["empresa_id"] in E else 0,
                                       format_func=lambda i: E[i]["nome_curto"])
        d0 = parse_data(f["data_laudo"])
        dsel = c1.date_input("Data do laudo", d0, format="DD/MM/YYYY")
        f["data_laudo"] = data_extenso(dsel)
        f["instrumentos"] = c2.text_input("Instrumentos usados na inspeção", f.get("instrumentos", "dosímetro de ruído"))
        f["agentes_obj"] = st.text_input("Agentes avaliados (frase do objetivo)", f["agentes_obj"])
        f["vci_ref"] = st.checkbox("A função conduz veículos: incluir metodologia de vibração de corpo inteiro (VCI)", f.get("vci_ref", False))

    # ---- Ambiente
    with tabs[1]:
        amb = st.text_area("Descrição do ambiente laborativo (separe parágrafos com uma linha em branco; aceita <b>negrito</b>)",
                           "\n\n".join(f["ambiente"]), height=220)
        f["ambiente"] = [p.strip() for p in re.split(r"\n\s*\n", amb) if p.strip()]
        f["atividades"] = st.text_area("Descrição das atividades", f["atividades"], height=140)

    # ---- Ruído
    with tabs[2]:
        r = f["ruido"]
        modo = st.radio("Como informar o ruído", ["Dose e tempo medidos (calcula o NE)", "NE e dose já calculados"],
                        index=0 if r.get("med") or not r.get("nen") else 1, horizontal=True)
        c1, c2, c3 = st.columns(3)
        if modo.startswith("Dose"):
            med = r.get("med") or ["", "", ""]
            D = c1.text_input("Dose medida D (%)", med[0] or "")
            T = c2.text_input("Tempo de medição T (min)", med[1] or "")
            nD, nT = num(D), num(T)
            if nD and nT and nD > 0 and nT > 0:
                proj, ne = calcula_ruido(nD, nT)
                c3.metric("NE projetado (480 min)", f"{fmt(ne, 2)} dB(A)")
                st.write(f"Dose projetada para 480 min: **{fmt(proj, 2)}%** · NE = 85 + 16,61 × log[(D × 480)/(100 × T)]")
                r = {"nen": fmt(ne, 1), "dose": fmt(proj, 2), "fonte": r.get("fonte", "Dosimetria"), "hist": None,
                     "acima": ne >= 80.05, "med": [D.strip(), T.strip(), fmt(ne, 2)]}
            else:
                st.info("Informe a dose e o tempo da medição.")
        else:
            nen = c1.text_input("NE (dB(A))", r.get("nen", ""))
            dose = c2.text_input("Dose 8 h (%)", r.get("dose", ""))
            v = num(nen)
            r = {"nen": nen, "dose": dose, "fonte": r.get("fonte", "Dosimetria"), "hist": None, "acima": bool(v and v >= 80.05)}
        r["fonte"] = st.text_input("Fonte / data (coluna da tabela)", r.get("fonte", "Dosimetria"))
        f["ruido"] = r
        if r.get("nen"):
            nv = num(r["nen"])
            if nv is not None and nv > 85:
                st.error("NE acima do limite de 85 dB(A): o texto automático de conclusão (\"abaixo do limite\") não se aplica. Revise.")
            elif r.get("acima"):
                st.warning("NE acima do nível de ação (80 dB(A)): o laudo incluirá o texto sobre protetor auricular e conservação auditiva.")

    # ---- Calor
    with tabs[3]:
        c = f["calor"]
        usa_tab = st.checkbox("Informar leituras de IBUTG (tabela)", value=bool(c.get("rows")))
        if usa_tab:
            c["data_leitura"] = st.text_input("Data das leituras", c.get("data_leitura", ""))
            base = pd.DataFrame(c.get("rows") or [["", "", "", "", "26,7", "Abaixo do limite"]],
                                columns=["Local", "tbn (°C)", "tg (°C)", "IBUTG (°C)", "Limite (°C)", "Resultado"])
            ed = st.data_editor(base, num_rows="dynamic", width='stretch', key="calor_ed")
            c["rows"] = ed.fillna("").astype(str).values.tolist()
            vals = [num(x[3]) for x in c["rows"] if num(x[3]) is not None]
            c["max"] = fmt(max(vals), 2) if vals else ""
        else:
            c["rows"] = None
        c["concl"] = st.text_area("Observação / conclusão do calor", c["concl"], height=110)
        f["calor"] = c

    # ---- Vibração
    with tabs[4]:
        vt = st.text_area("Texto da vibração (parágrafos separados por linha em branco; aceita <super>1,75</super>)",
                          "\n\n".join(f["vibracao"]), height=150)
        f["vibracao"] = [p.strip() for p in re.split(r"\n\s*\n", vt) if p.strip()]
        use_vt = st.checkbox("Incluir tabela de referência (aren / VDVR)", value=bool(f.get("vib_tab")))
        if use_vt:
            base = pd.DataFrame(f.get("vib_tab") or [["aren", "0,5 m/s²", "1,1 m/s²", ""], ["VDVR", "9,1 m/s<super>1,75</super>", "21,0 m/s<super>1,75</super>", ""]],
                                columns=["Parâmetro", "Nível de Ação", "Limite de Exposição", "Referência"])
            ed = st.data_editor(base, num_rows="dynamic", width='stretch', key="vib_ed")
            f["vib_tab"] = ed.fillna("").astype(str).values.tolist()
        else:
            f["vib_tab"] = None
        f["vib_concl"] = st.text_area("Conclusão da vibração (após \"Conclusão:\")", f["vib_concl"], height=80)

    # ---- Químicos
    with tabs[5]:
        q = f["quim"]
        modo_q = "Sem exposição (observação)"
        if q.get("res"):
            modo_q = "Quantitativo (resultados de laboratório)"
        elif q.get("rows"):
            modo_q = "Qualitativo (tabela de contato)"
        modo_q = st.radio("Situação dos agentes químicos", ["Sem exposição (observação)", "Qualitativo (tabela de contato)",
                                                            "Quantitativo (resultados de laboratório)"],
                          index=["Sem exposição (observação)", "Qualitativo (tabela de contato)", "Quantitativo (resultados de laboratório)"].index(modo_q))
        q["intro"] = st.text_area("Texto de abertura do item 8", q.get("intro", ""), height=130)
        if modo_q.startswith("Sem"):
            q = {"rows": None, "intro": q["intro"], "concl": None}
        elif modo_q.startswith("Qualit"):
            base = pd.DataFrame(q.get("rows") or [["", "Intermitente", "Dérmica", "Creme protetor para as mãos"]],
                                columns=["Agente / fonte", "Frequência", "Via", "Controle (EPI)"])
            ed = st.data_editor(base, num_rows="dynamic", width='stretch', key="q_ql")
            q = {"rows": ed.fillna("").astype(str).values.tolist(), "intro": q["intro"],
                 "concl": st.text_area("Conclusão do item 8", q.get("concl") or "", height=140)}
        else:
            rows = []
            for cap, hdr, rws in (q.get("res") or []):
                three = len(hdr) == 3
                unit = re.search(r"\((.*?)\)", hdr[1])
                un = unit.group(1) if unit else ""
                for rw in rws:
                    rows.append({"Grupo (título da tabela)": cap, "Agente": re.sub(r"</?b>", "", rw[0]), "Resultado": rw[1], "Unidade": un,
                                 "LEO ACGIH": "" if three else rw[2], "LEO NR-15": "" if three else rw[3], "LEO adotado": rw[2] if three else ""})
            if not rows:
                rows = [{"Grupo (título da tabela)": "", "Agente": "", "Resultado": "", "Unidade": "mg/m³", "LEO ACGIH": "", "LEO NR-15": "", "LEO adotado": ""}]
            st.caption("Uma linha por agente. Linhas com o mesmo \"Grupo\" formam uma tabela. Preencha **LEO ACGIH** e **LEO NR-15**, "
                       "ou apenas **LEO adotado** (tabela com um só limite).")
            ed = st.data_editor(pd.DataFrame(rows), num_rows="dynamic", width='stretch', key="q_qt", height=380)
            ed = ed.fillna("").astype(str)
            groups = {}
            for _, rw in ed.iterrows():
                if not rw["Agente"].strip():
                    continue
                groups.setdefault((rw["Grupo (título da tabela)"], rw["Unidade"]), []).append(rw)
            res = []
            for (cap, un), rs in groups.items():
                if any(x["LEO adotado"].strip() for x in rs):
                    res.append([cap, ["Agente químico", f"Resultado ({un})", f"LEO adotado ({un})"], [[x["Agente"], x["Resultado"], x["LEO adotado"] or "–"] for x in rs]])
                else:
                    res.append([cap, ["Agente químico", f"Resultado ({un})", f"LEO ACGIH ({un})", f"LEO NR-15 ({un})"],
                                [[x["Agente"], x["Resultado"], x["LEO ACGIH"] or "–", x["LEO NR-15"] or "–"] for x in rs]])
            q = {"rows": None, "intro": q["intro"], "res": res,
                 "coleta_txt": st.text_area("Frase da diligência sobre a coleta (seção 3)", q.get("coleta_txt", "A avaliação quantitativa dos agentes químicos foi realizada em [data], por laboratório especializado, conforme descrito no item 8."), height=80),
                 "concl": st.text_area("Conclusão do item 8", q.get("concl") or "", height=170)}
        f["quim"] = q

    # ---- Medidas e síntese
    with tabs[6]:
        f["epc"] = st.text_area("Item 10 – EPC e medidas de controle", f["epc"], height=110)
        f["epi"] = st.text_area("Item 11 – EPI", f["epi"], height=110)
        st.markdown("**Síntese (item 12)** — o ruído é preenchido automaticamente; use `<br/>` para quebrar linha.")
        s = list(f.get("sint") or ["", "", "", ""])
        c1, c2, c3 = st.columns(3)
        s[1] = c1.text_input("Calor", s[1])
        s[2] = c2.text_input("Agentes químicos", s[2])
        s[3] = c3.text_input("Vibração", s[3])
        if f["ruido"].get("nen"):
            s[0] = f"{f['ruido']['nen']} dB(A)<br/>(LT 85)"
        f["sint"] = s
        rec = st.text_area("Recomendações (uma por linha; campo interno, não é impresso no laudo)", "\n".join(f.get("rec") or []), height=110)
        f["rec"] = [x.strip() for x in rec.split("\n") if x.strip()]

    # ---- Textos do laudo (todos os textos fixos do modelo, editáveis)
    with tabs[7]:
        st.write("O sistema redige estes textos automaticamente. Se precisar, **edite qualquer um**: o texto alterado passa a valer neste laudo. "
                 "Para **voltar ao texto automático**, apague tudo na caixa e salve. Aceita `<b>negrito</b>`, `<i>itálico</i>` e `<br/>`.")
        st.caption("Atenção: um texto editado deixa de acompanhar as mudanças nos dados (por exemplo, o valor do NE citado na conclusão). "
                   "Se alterar os dados depois, revise os textos editados.")
        ROTULOS = {
            "fundamentacao": "Capa – Fundamentação legal e normativa",
            "objetivo": "2. Objetivo",
            "diligencia": "3. Diligência e caracterização (1º parágrafo)",
            "exposicao": "3. Exposição (habitualidade e permanência)",
            "met_ruido": "4. Metodologia – Ruído",
            "met_calor": "4. Metodologia – Calor",
            "met_vci": "4. Metodologia – Vibração de corpo inteiro",
            "met_quim": "4. Metodologia – Agentes químicos e biológicos",
            "ruido_intro": "7.1 Ruído – texto de introdução",
            "ruido_concl": "7.1 Ruído – Conclusão",
            "quim_sem": "8. Agentes químicos – texto final (quando não há tabela)",
            "bio": "9. Agentes biológicos",
            "sint_nota": "12. Síntese – nota abaixo da tabela",
            "conclusao1": "13. Conclusão – 1º parágrafo",
            "conclusao2": "13. Conclusão – 2º parágrafo",
            "encerramento": "14. Encerramento",
        }
        try:
            padrao = {}
            emp_t = copy.deepcopy(E[f["empresa_id"]])
            sig_t = store.obter_signatario()
            f_t = copy.deepcopy(f)
            f_t["textos"] = {}
            engine.build(emp_t, sig_t, f_t, f["data_laudo"], None, coletar=padrao)
        except Exception as e_t:
            padrao = {}
            st.warning(f"Preencha os dados básicos do laudo (função, empresa, ruído) para liberar a edição dos textos. ({e_t})")
        txs = dict(f.get("textos") or {})
        idl = f.get("id") or "novo"
        for k, padrao_k in padrao.items():
            atual = txs.get(k) or padrao_k
            editado = k in txs and txs[k] and txs[k] != padrao_k
            rot = ROTULOS.get(k, k) + ("  ✏️ editado" if editado else "")
            novo_v = st.text_area(rot, atual, height=max(90, min(320, 22 * (len(atual) // 95 + 2))), key=f"tx_{idl}_{k}")
            if not novo_v.strip():
                txs.pop(k, None)
            elif novo_v != padrao_k:
                txs[k] = novo_v
            else:
                txs.pop(k, None)
        f["textos"] = txs
        if txs:
            st.info(f"{len(txs)} texto(s) editado(s) neste laudo.")

    st.divider()
    cs, cg = st.columns(2)
    salvar = cs.button("💾 Salvar", type="primary", width='stretch')
    gerar = cg.button("📄 Salvar e gerar PDF", width='stretch') or st.session_state.pop("auto_gerar", False)

    def salvar_laudo():
        if not f["nome"].strip():
            st.error("Informe o nome da função.")
            return False
        if not f["id"]:
            f["id"] = slug(f["nome"]).lower()
            base, i = f["id"], 2
            while store.existe("laudo", f["id"]):
                f["id"] = f"{base}_{i}"
                i += 1
        f["key"] = slug(f["nome"])
        store.salvar("laudo", f["id"], f)
        st.session_state.sel = f["id"]
        return True

    if salvar or gerar:
        if not f["ruido"].get("nen"):
            st.error("Informe o ruído (dose e tempo, ou NE e dose) antes de salvar.")
        elif salvar_laudo():
            st.success("Laudo salvo.")
            if gerar:
                emp = copy.deepcopy(E[f["empresa_id"]])
                store.logo_para_arquivo(emp)
                sig = store.obter_signatario()
                saida = os.path.join(D_OUT, f"LTCAT_{f['key']}_{emp['id'].upper()}.pdf")
                try:
                    engine.build(emp, sig, f, f["data_laudo"], saida)
                    st.success(f"PDF gerado: {saida}")
                    with open(saida, "rb") as fh:
                        st.download_button("⬇️ Baixar PDF", fh.read(), file_name=os.path.basename(saida), mime="application/pdf")
                    import pymupdf
                    doc = pymupdf.open(saida)
                    st.caption(f"{len(doc)} páginas")
                    cols = st.columns(min(len(doc), 4))
                    for i, p in enumerate(doc):
                        cols[i % len(cols)].image(p.get_pixmap(dpi=70).tobytes("png"), caption=f"Página {i + 1}")
                except Exception as ex:
                    st.error(f"Erro ao gerar o PDF: {ex}")

# ================================================================== EMPRESAS
elif pagina == "Empresas":
    st.title("Empresas")
    E = empresas()
    ids = list(E) + ["__nova__"]
    eid = st.selectbox("Empresa", ids, format_func=lambda i: "➕ Nova empresa" if i == "__nova__" else E[i]["nome_curto"])
    e = copy.deepcopy(E.get(eid)) if eid != "__nova__" else {"id": "", "nome_curto": "", "razao": "", "endereco": "", "endereco_curto": "",
                                                              "rodape": "", "cnpj": "", "cnae": "", "grau_risco": "3", "cidade": "", "logo": ""}
    c1, c2 = st.columns(2)
    e["nome_curto"] = c1.text_input("Nome curto (cabeçalho das páginas)", e["nome_curto"])
    e["razao"] = c2.text_input("Razão social", e["razao"])
    e["cnpj"] = c1.text_input("CNPJ", e["cnpj"])
    e["grau_risco"] = c2.text_input("Grau de risco", e["grau_risco"])
    e["cnae"] = st.text_input("CNAE / atividade", e["cnae"])
    e["endereco"] = st.text_input("Endereço completo (quadro de identificação)", e["endereco"])
    e["endereco_curto"] = st.text_input("Endereço curto (texto da diligência)", e["endereco_curto"])
    e["rodape"] = st.text_input("Rodapé das páginas", e["rodape"])
    e["cidade"] = c1.text_input("Cidade (assinatura)", e["cidade"])
    st.write("Logo atual:", e.get("logo") or "—")
    if e.get("logo_b64"):
        import base64 as _b64
        st.image(_b64.b64decode(e["logo_b64"]), width=200)
    elif e.get("logo") and os.path.exists(os.path.join(ROOT, e["logo"])):
        st.image(os.path.join(ROOT, e["logo"]), width=200)
    up = st.file_uploader("Trocar logo (PNG ou JPG)", type=["png", "jpg", "jpeg"])
    if st.button("💾 Salvar empresa", type="primary"):
        if not e["nome_curto"]:
            st.error("Informe o nome curto.")
        else:
            if not e["id"]:
                e["id"] = slug(e["nome_curto"]).lower()[:30]
            if up is not None:
                store.guardar_logo(e, up.name, up.getvalue())
            store.salvar("empresa", e["id"], e)
            st.success("Empresa salva.")

# ================================================================== SIGNATÁRIO
elif pagina == "Signatário":
    st.title("Signatário (responsável técnico)")
    sig = store.obter_signatario()
    sig["nome"] = st.text_input("Nome", sig.get("nome", ""))
    sig["titulo"] = st.text_input("Título", sig.get("titulo", ""))
    sig["crea"] = st.text_input("Registro (ex.: CREA 0000000000 - SP)", sig.get("crea", ""))
    if st.button("💾 Salvar", type="primary"):
        store.salvar_signatario(sig)
        st.success("Salvo.")

# ================================================================== MONTAR LAUDO
elif pagina == "Montar laudo":
    st.title("Montar laudo a partir de documentos")
    st.write("Escolha a empresa e a função, envie **todos os documentos** dessa função (laudos anteriores, avaliações ambientais, planilhas ou fotos de "
             "medições, descrição de atividades). O sistema monta o rascunho completo, marca as pendências e os alertas, e você confere antes de gerar o PDF.")
    E = empresas()
    if not E:
        st.error("Cadastre uma empresa primeiro (menu Empresas).")
        st.stop()
    c1, c2, c3 = st.columns(3)
    mt_emp = c1.selectbox("Empresa", list(E), format_func=lambda i: E[i]["nome_curto"], key="mt_emp")
    mt_funcao = c2.text_input("Função", placeholder="ex.: Mecânico", key="mt_funcao")
    mt_data = c3.date_input("Data do laudo", date.today(), format="DD/MM/YYYY", key="mt_data")
    mt_extras = st.text_area("Instruções para a montagem (opcional)", key="mt_extras", height=80,
                             placeholder="ex.: usar só o limite da NR-15 para o chumbo; ruído: dose 4,5% em 47 min; calor: observação padrão")
    arqs = st.file_uploader("Documentos da função (PDF, Word, texto ou imagem)", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"],
                            accept_multiple_files=True, key="mt_arqs")
    docs, resumo = [], []
    cache = st.session_state.setdefault("mt_cache", {})
    for a in arqs or []:
        nm, dados = a.name, a.getvalue()
        ext = os.path.splitext(nm.lower())[1]
        if ext in (".png", ".jpg", ".jpeg"):
            import base64
            import io
            from PIL import Image as _PI
            im = _PI.open(io.BytesIO(dados)).convert("RGB")
            im.thumbnail((1700, 1700))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            docs.append({"nome": nm, "texto": "", "imagens": [base64.b64encode(buf.getvalue()).decode()], "bytes": None})
            resumo.append({"Arquivo": nm, "Tipo": "imagem", "Leitura": "1 imagem"})
            continue
        chave = (nm, len(dados))
        if chave not in cache:
            cache[chave] = ex_.ler_arquivo(nm, dados)
        info = cache[chave]
        if info["digitalizado"]:
            faixa = st.text_input(f"Páginas de «{nm}» (PDF digitalizado, {info['paginas']} págs.)", f"1-{min(info['paginas'], 6)}", key=f"mt_pg_{nm}")
            pags = []
            for parte in faixa.split(","):
                m = re.match(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*$", parte)
                if m:
                    a_, b_ = int(m.group(1)), int(m.group(2) or m.group(1))
                    pags += [p - 1 for p in range(a_, b_ + 1) if 1 <= p <= info["paginas"]]
            pags = sorted(set(pags))[:20]
            docs.append({"nome": nm, "texto": "", "imagens": ex_.imagens_paginas(dados, pags) if pags else [], "bytes": dados, "paginas": pags})
            resumo.append({"Arquivo": nm, "Tipo": "PDF digitalizado", "Leitura": f"{len(pags)} página(s) como imagem (só a IA lê)"})
        else:
            docs.append({"nome": nm, "texto": info["texto"], "imagens": [], "bytes": dados if ext == ".pdf" else None})
            resumo.append({"Arquivo": nm, "Tipo": info["tipo"].upper(), "Leitura": f"{len(info['texto'])} caracteres de texto"})
    if resumo:
        st.dataframe(pd.DataFrame(resumo), width='stretch', hide_index=True)
    tem_chave = bool(ex_.chave_api())
    st.info("🔒 A montagem **com IA** envia o conteúdo dos documentos (texto e imagens) à API da Anthropic. A montagem **sem IA** roda só no seu computador.")
    if not tem_chave:
        st.warning("Chave da API não configurada (menu **Configurações**). Sem ela só está disponível a montagem sem IA.")
    b1, b2 = st.columns(2)
    pronto = bool(docs) and bool(mt_funcao.strip())
    data_txt = data_extenso(mt_data)
    if b1.button("🤖 Montar com IA", type="primary", disabled=not (pronto and tem_chave), width='stretch'):
        try:
            with st.spinner("A IA está lendo os documentos e montando o rascunho (pode levar 1 a 3 minutos)..."):
                simp = MT.montar_com_ia(docs, E[mt_emp]["nome_curto"], mt_funcao.strip(), data_txt, mt_extras)
            st.session_state.mt_res = MT.para_laudo(simp, mt_emp, mt_funcao.strip(), data_txt, slug)
        except Exception as e:
            st.error(f"Falha na montagem com IA: {e}")
    if b2.button("📖 Montar sem IA (formatos conhecidos)", disabled=not pronto, width='stretch'):
        with st.spinner("Lendo os documentos..."):
            simp = MT.montar_sem_ia(docs, mt_funcao.strip(), data_txt)
        st.session_state.mt_res = MT.para_laudo(simp, mt_emp, mt_funcao.strip(), data_txt, slug)
    if not pronto:
        st.caption("Informe a função e envie ao menos um documento.")

    res = st.session_state.get("mt_res")
    if res:
        f, alertas = res
        st.divider()
        st.subheader(f"Rascunho: {f['nome']}")
        ordem = {"alta": 0, "media": 1, "baixa": 2}
        if alertas:
            st.markdown("**Pendências e alertas**")
            for nivel, msg in sorted(alertas, key=lambda x: ordem.get(x[0], 3)):
                (st.error if nivel == "alta" else st.warning if nivel == "media" else st.info)(msg)
        else:
            st.success("Nenhuma pendência identificada. Confira mesmo assim.")
        st.markdown("**Confira e ajuste os textos principais** (os demais campos você ajusta no editor)")
        f["ident_setor"] = st.text_input("Setor / Função", f["ident_setor"], key="mt_e_id")
        f["setor"] = st.text_input("Setor (capa)", f["setor"], key="mt_e_set")
        f["atividades"] = st.text_area("Atividades", f["atividades"], height=110, key="mt_e_at")
        amb = st.text_area("Ambiente (parágrafos separados por linha em branco)", "\n\n".join(f["ambiente"]), height=140, key="mt_e_am")
        f["ambiente"] = [p.strip() for p in re.split(r"\n\s*\n", amb) if p.strip()]
        r = f["ruido"]
        st.write(f"**Ruído:** NE {r.get('nen') or '—'} dB(A) · dose 8 h {r.get('dose') or '—'}%" + (f" · medição: D {r['med'][0]}% em {r['med'][1]} min" if r.get("med") else ""))
        st.write("**Calor:** " + (f["calor"]["concl"][:160] + "…"))
        if f["quim"].get("res"):
            st.write("**Químicos:** " + "; ".join(f"{c} ({len(rows)} agentes)" for c, _, rows in f["quim"]["res"]))
            f["quim"]["concl"] = st.text_area("Conclusão do item 8 (químicos)", f["quim"].get("concl") or "", height=150, key="mt_e_qc")
        elif f["quim"].get("rows"):
            st.write("**Químicos (qualitativo):** " + "; ".join(x[0][:50] for x in f["quim"]["rows"]))
            f["quim"]["concl"] = st.text_area("Conclusão do item 8 (químicos)", f["quim"].get("concl") or "", height=120, key="mt_e_qc2")
        else:
            st.write("**Químicos:** sem exposição (observação).")
        f["epc"] = st.text_area("EPC e medidas de controle (item 10)", f["epc"], height=90, key="mt_e_epc")
        f["epi"] = st.text_area("EPI (item 11)", f["epi"], height=90, key="mt_e_epi")
        rec = st.text_area("Recomendações (uma por linha; campo interno, não é impresso no laudo)", "\n".join(f["rec"]), height=90, key="mt_e_rec")
        f["rec"] = [x.strip() for x in rec.split("\n") if x.strip()]
        st.session_state.mt_res = (f, alertas)
        d1, d2 = st.columns(2)
        if d1.button("👁️ Pré-visualizar PDF", width='stretch'):
            try:
                emp = copy.deepcopy(E[f["empresa_id"]])
                store.logo_para_arquivo(emp)
                sig = store.obter_signatario()
                prev = os.path.join(D_OUT, "_previa.pdf")
                engine.build(emp, sig, f, f["data_laudo"], prev)
                import pymupdf
                dd = pymupdf.open(prev)
                cols = st.columns(min(len(dd), 4))
                for i, p in enumerate(dd):
                    cols[i % len(cols)].image(p.get_pixmap(dpi=70).tobytes("png"), caption=f"Página {i + 1}")
                dd.close()
            except Exception as ex:
                st.error(f"Erro ao gerar a prévia: {ex}")
        if d2.button("💾 Salvar como laudo", type="primary", width='stretch'):
            base_id, i_ = f["id"], 2
            while store.existe("laudo", f["id"]):
                f["id"] = f"{base_id}_{i_}"
                i_ += 1
            store.salvar("laudo", f["id"], f)
            st.session_state.mt_salvo = f["id"]
            st.success(f"Laudo salvo ({f['id']}). Abra no editor para ajustes finos e para gerar o PDF.")
        if st.session_state.get("mt_salvo"):
            st.button("✏️ Abrir o laudo salvo no editor", on_click=ir_editar, args=(st.session_state.mt_salvo,))

# ================================================================== LER DOCUMENTOS
elif pagina == "Ler documentos":
    st.title("Ler documentos")
    st.write("Envie laudos anteriores, avaliações ambientais ou descrições de atividades. A IA lê o documento e propõe as medições, "
             "atividades e resultados; você confere cada linha e só então aplica ao laudo.")
    up = st.file_uploader("Documento (PDF, Word ou texto)", type=["pdf", "docx", "txt"])
    if up is not None and st.session_state.get("doc_nome") != up.name + str(up.size):
        with st.spinner("Lendo o arquivo..."):
            info = ex_.ler_arquivo(up.name, up.getvalue())
        st.session_state.update({"doc_nome": up.name + str(up.size), "doc_info": info, "doc_bytes": up.getvalue(), "doc_arquivo": up.name,
                                 "extr": None, "ocr_txt": None})
    info = st.session_state.get("doc_info")
    if up is None:
        info = None
    if info:
        st.success(f"{st.session_state.doc_arquivo}: {info['paginas']} página(s)" + (" — PDF digitalizado (sem texto)" if info["digitalizado"] else ""))
        usar_img, pags = False, []
        if info["digitalizado"]:
            modo = st.radio("Como ler este PDF digitalizado", ["Enviar as páginas como imagem para a IA (melhor para tabelas)",
                                                              "OCR local no computador (só texto, sem enviar imagens)"])
            faixa = st.text_input("Páginas (ex.: 14-20 ou 3,5,8)", f"1-{min(info['paginas'], 8)}")
            for parte in faixa.split(","):
                m = re.match(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*$", parte)
                if m:
                    a_, b_ = int(m.group(1)), int(m.group(2) or m.group(1))
                    pags += [p - 1 for p in range(a_, b_ + 1) if 1 <= p <= info["paginas"]]
            pags = sorted(set(pags))[:25]
            st.caption(f"{len(pags)} página(s) selecionada(s) (máx. 25 por leitura).")
            usar_img = modo.startswith("Enviar")
            if not usar_img and pags and st.button("Executar OCR nas páginas selecionadas"):
                import pymupdf
                with st.spinner("OCR em andamento..."):
                    d = pymupdf.open(stream=st.session_state.doc_bytes, filetype="pdf")
                    st.session_state.ocr_txt = ex_.ocr_paginas(d, pags)
        texto = info["texto"] or st.session_state.get("ocr_txt") or ""
        ctx = st.text_input("Contexto para a IA (opcional)", placeholder="ex.: avaliação química da unidade Sorocaba; interessam Funilaria e Elétrica")
        tem_chave = bool(ex_.chave_api())
        st.info("🔒 Ao extrair com a IA, o conteúdo enviado (texto ou imagens das páginas) é transmitido à API da Anthropic. "
                "O OCR local e o modo manual não enviam nada.")
        if not tem_chave:
            st.warning("Chave da API não configurada. Use o menu **Configurações** ou o **modo manual** abaixo.")
        bloqueado = (not tem_chave) or (info["digitalizado"] and usar_img and not pags) or (info["digitalizado"] and not usar_img and not texto)
        if st.button("🤖 Extrair com IA", type="primary", disabled=bloqueado):
            try:
                with st.spinner("A IA está lendo o documento..."):
                    imgs = ex_.imagens_paginas(st.session_state.doc_bytes, pags) if (info["digitalizado"] and usar_img) else None
                    st.session_state.extr = ex_.extrair_com_ia(texto=None if imgs else texto, imagens_b64=imgs, contexto=ctx)
            except Exception as e:
                st.error(f"Falha na extração: {e}")
        st.caption("**Leitura local**: lê direto os formatos conhecidos (LTCAT City/STU e avaliações químicas em tabelas), sem IA e sem enviar nada para fora.")
        if st.button("📖 Leitura local (sem IA)", type="primary" if not tem_chave else "secondary", disabled=not texto and info["digitalizado"]):
            with st.spinner("Lendo o documento..."):
                res_loc = LL.leitura_local(texto, st.session_state.doc_bytes if info.get("tipo") == "pdf" else None, st.session_state.doc_arquivo)
            st.session_state.extr = res_loc
            n_ = {k: len(v) for k, v in res_loc.items() if isinstance(v, list)}
            if not any(n_.values()):
                st.warning("Não reconheci o formato deste documento. Use a leitura por IA ou o modo manual.")
            else:
                st.success("Leitura concluída: " + ", ".join(f"{v} {k}" for k, v in n_.items() if v) + ". Confira abaixo.")
        with st.expander("Modo manual (sem chave de API): usar a IA numa conversa e colar o JSON aqui"):
            st.write("1) Copie as instruções abaixo; 2) cole numa conversa com a IA junto com o documento; 3) cole aqui o JSON que ela devolver.")
            st.code(ex_.SCHEMA_PROMPT, language="text")
            colado = st.text_area("JSON devolvido pela IA", height=160, key="json_manual")
            if st.button("Carregar JSON colado"):
                if not colado.strip():
                    st.warning("Cole primeiro, na caixa acima, o JSON que a IA devolveu.")
                else:
                    try:
                        st.session_state.extr = ex_.normalizar(ex_._json_da_resposta(colado))
                    except Exception as e:
                        st.error(f"JSON inválido: {e}")
        with st.expander("Texto extraído do documento"):
            busca = st.text_input("Buscar (ex.: função, dB, IBUTG, mg/m³)")
            if busca:
                for l in [x for x in re.split(r"(?<=[.\n])", texto) if busca.lower() in x.lower()][:60]:
                    st.code(l.strip()[:600])
            st.text_area("Texto completo", texto, height=260)

    ex = st.session_state.get("extr")
    if ex:
        st.divider()
        st.subheader("Conferência dos dados extraídos")
        st.caption("Marque apenas o que está correto. Corrija valores direto nas tabelas. Nada é aplicado até você clicar em Aplicar.")
        doc = ex["documento"]
        c1, c2, c3 = st.columns(3)
        doc["tipo"] = c1.text_input("Tipo do documento", doc.get("tipo") or "")
        doc["data"] = c2.text_input("Data do documento", doc.get("data") or "")
        doc["responsavel_tecnico"] = c3.text_input("Responsável técnico", doc.get("responsavel_tecnico") or "")
        doc["arquivo"] = st.session_state.get("doc_arquivo", "")

        def tabela(chave, colunas, key):
            linhas = ex.get(chave) or []
            df = pd.DataFrame([{"Importar": True, **{c: (str(l.get(c)) if l.get(c) is not None else "") for c in colunas}} for l in linhas],
                              columns=["Importar"] + colunas)
            return st.data_editor(df, num_rows="dynamic", width='stretch', key=key, hide_index=True)

        t_f, t_r, t_q, t_c, t_v, t_e = st.tabs(["Funções", "Ruído", "Químicos", "Calor", "Vibração", "EPI"])
        with t_f:
            ed_f = tabela("funcoes", ["nome", "setor", "atividades", "ambiente"], "ed_f")
        with t_r:
            ed_r = tabela("ruido", ["funcao", "nen_dBA", "dose_pct", "tempo_medicao_min", "limite_dBA", "trecho"], "ed_r")
        with t_q:
            ed_q = tabela("quimicos", ["setor_funcao", "grupo", "agente", "resultado", "unidade", "leo_acgih", "leo_nr15", "periodo", "trecho"], "ed_q")
        with t_c:
            ed_c = tabela("calor", ["local", "funcao", "tbn", "tg", "ibutg", "limite", "data", "trecho"], "ed_c")
        with t_v:
            ed_v = tabela("vibracao", ["funcao", "aren", "vdvr", "data", "trecho"], "ed_v")
        with t_e:
            ed_e = tabela("epi", ["funcao", "epi", "trecho"], "ed_e")

        st.markdown("#### Aplicar ao laudo")
        L = laudos()
        alvo = st.selectbox("Laudo de destino", ["(selecione)"] + list(L), format_func=lambda i: i if i == "(selecione)" else L[i]["nome"])
        sel_f = ed_f[ed_f["Importar"]] if len(ed_f) else ed_f
        sel_r = ed_r[ed_r["Importar"]] if len(ed_r) else ed_r
        sel_q = ed_q[ed_q["Importar"]] if len(ed_q) else ed_q
        sel_c = ed_c[ed_c["Importar"]] if len(ed_c) else ed_c
        sel_v = ed_v[ed_v["Importar"]] if len(ed_v) else ed_v
        O_AT, O_RU, O_QU, O_CA, O_VI = ("Atividades e ambiente (1ª função marcada)", "Ruído (1ª linha marcada)",
                                        "Agentes químicos (todas as linhas marcadas)", "Calor (linhas marcadas)", "Vibração (1ª linha marcada)")
        opc = st.multiselect("O que aplicar", [O_AT, O_RU, O_QU, O_CA, O_VI],
                             default=[o for o, n in [(O_AT, len(sel_f)), (O_RU, len(sel_r)), (O_QU, len(sel_q)), (O_CA, len(sel_c)), (O_VI, len(sel_v))] if n])

        def aplicar_selecao(f, avisar=True):
            """Aplica ao laudo `f` as linhas marcadas; devolve a lista do que foi feito."""
            feitos = []
            if O_AT in opc and len(sel_f):
                it = sel_f.iloc[0].to_dict()
                feitos.append(ex_.aplicar_atividades(f, it))
                ex_.registrar_origem(f, "atividades/ambiente", doc, it.get("atividades", ""))
            if O_RU in opc and len(sel_r):
                it = sel_r.iloc[0].to_dict()
                msg = ex_.aplicar_ruido(f, {"nen_dBA": it.get("nen_dBA"), "dose_pct": it.get("dose_pct"), "tempo_medicao_min": it.get("tempo_medicao_min")})
                if msg:
                    feitos.append(msg)
                    ex_.registrar_origem(f, "ruído", doc, it.get("trecho", ""))
                    if not (str(it.get("dose_pct") or "").strip() and str(it.get("tempo_medicao_min") or "").strip()):
                        feitos.append("(atenção: ruído sem dose/tempo — o NE foi lido do documento; confirme a normalização para 8 h)")
                elif avisar:
                    st.warning("A linha de ruído não tem dose/tempo nem NE: nada foi aplicado ao ruído.")
            if O_QU in opc and len(sel_q):
                itens = [r.to_dict() for _, r in sel_q.iterrows()]
                feitos.append(ex_.aplicar_quimicos(f, itens))
                ex_.registrar_origem(f, "agentes químicos", doc, "; ".join(sorted({str(i.get("grupo") or "") for i in itens}))[:200])
            if O_CA in opc and len(sel_c):
                feitos.append(ex_.aplicar_calor(f, [r.to_dict() for _, r in sel_c.iterrows()], doc.get("data", "")))
                ex_.registrar_origem(f, "calor", doc, "")
            if O_VI in opc and len(sel_v):
                it = sel_v.iloc[0].to_dict()
                msg = LL.aplicar_vibracao(f, it)
                if msg:
                    feitos.append(msg)
                    ex_.registrar_origem(f, "vibração", {**doc, "data": it.get("data") or doc.get("data", "")}, it.get("trecho", ""))
            return [x for x in feitos if x]
        if st.button("✅ Aplicar ao laudo", type="primary", disabled=alvo == "(selecione)" or not opc):
            f = copy.deepcopy(L[alvo])
            ano_laudo = ex_.ano(f.get("data_laudo"))
            feitos = aplicar_selecao(f)
            store.salvar("laudo", f["id"], f)
            st.success("Aplicado e salvo em " + L[alvo]["nome"] + ": " + "; ".join(feitos))
            if ex_.ano(doc.get("data")) and ano_laudo and ex_.ano(doc.get("data")) != ano_laudo:
                st.warning(f"O documento é de {doc.get('data')} e o laudo é de {f['data_laudo']}. Esses dados ficam marcados como de origem anterior "
                           "no editor. Confirme se foram remedidos antes de emitir o laudo como medição do dia.")
            st.info("Abra o menu **Editar laudo** para revisar os textos de conclusão e gerar o PDF.")

        st.markdown("#### Ou criar um laudo novo com estes dados")
        E_ = empresas()
        if not len(sel_f):
            st.caption("Marque ao menos uma função na aba **Funções** para criar um laudo novo.")
        elif not E_:
            st.caption("Cadastre uma empresa primeiro.")
        else:
            nomes = [str(r["nome"]) for _, r in sel_f.iterrows()]
            cA, cB, cC = st.columns(3)
            esc = cA.selectbox("Função do novo laudo", nomes)
            emp_novo = cB.selectbox("Empresa", list(E_), format_func=lambda i: E_[i]["nome_curto"], key="emp_novo")
            data_nova = cC.date_input("Data do laudo", date.today(), format="DD/MM/YYYY", key="data_nova")
            linha = sel_f[sel_f["nome"].astype(str) == esc].iloc[0].to_dict()
            if st.button("➕ Criar laudo novo", type="primary"):
                f = novo_laudo(emp_novo)
                f["nome"] = esc.upper()
                f["setor"] = str(linha.get("setor") or "")
                f["ident_setor"] = f"{f['setor']} / {esc.capitalize()}".strip(" /")
                f["data_laudo"] = data_extenso(data_nova)
                f["id"] = slug(f["nome"]).lower()
                base_id, i_ = f["id"], 2
                while store.existe("laudo", f["id"]):
                    f["id"] = f"{base_id}_{i_}"
                    i_ += 1
                f["key"] = slug(f["nome"])
                # restringe as linhas à função escolhida, quando o documento traz várias
                def so_funcao(df, col):
                    if len(df) and col in df.columns:
                        m_ = df[df[col].astype(str).str.lower().str.contains(esc.lower()[:5], na=False)]
                        return m_ if len(m_) else df
                    return df
                sel_f_bak, sel_r_bak, sel_v_bak = sel_f, sel_r, sel_v
                sel_f, sel_r, sel_v = sel_f[sel_f["nome"].astype(str) == esc], so_funcao(sel_r, "funcao"), so_funcao(sel_v, "funcao")
                feitos = aplicar_selecao(f, avisar=False)
                sel_f, sel_r, sel_v = sel_f_bak, sel_r_bak, sel_v_bak
                store.salvar("laudo", f["id"], f)
                st.success(f"Laudo \"{f['nome']}\" criado: " + "; ".join(feitos))
                if ex_.ano(doc.get("data")) and ex_.ano(doc.get("data")) != data_nova.year:
                    st.warning(f"Os dados vêm de um documento de {doc.get('data')} e o laudo novo é de {data_extenso(data_nova)}. Confirme se foram "
                               "remedidos antes de emitir o laudo como medição do dia (o editor mostra a origem de cada dado).")
                st.session_state.criado_id = f["id"]
            if st.session_state.get("criado_id"):
                st.button("✏️ Abrir o laudo criado no editor", on_click=ir_editar, args=(st.session_state.criado_id,))

# ================================================================== CONFIGURAÇÕES
else:
    st.title("Configurações")
    cfg = ex_.carregar_config()
    st.write("A leitura automática usa a API da Anthropic (Claude). A chave fica gravada apenas neste computador, em `dados/config.json` "
             "(texto simples; mantenha esta pasta protegida). Você também pode usar a variável de ambiente `ANTHROPIC_API_KEY`.")
    nova = st.text_input("Chave da API", value="", type="password", placeholder="sk-ant-... (deixe em branco para manter a atual)")
    st.caption("Chave atual: " + ("definida" if ex_.chave_api() else "não definida"))
    cfg["modelo"] = st.text_input("Modelo", cfg.get("modelo", ex_.MODELO_PADRAO))
    c1, c2 = st.columns(2)
    if c1.button("💾 Salvar", type="primary"):
        if nova.strip():
            cfg["anthropic_api_key"] = nova.strip()
        ex_.salvar_config(cfg)
        st.success("Configurações salvas.")
    if c2.button("🔌 Testar conexão"):
        try:
            import anthropic
            cli = anthropic.Anthropic(api_key=nova.strip() or ex_.chave_api())
            r = cli.messages.create(model=cfg["modelo"], max_tokens=10, messages=[{"role": "user", "content": "Responda apenas: ok"}])
            st.success("Conexão ok: " + "".join(b.text for b in r.content if getattr(b, "type", "") == "text")[:40])
        except Exception as e:
            st.error(f"Falha na conexão: {e}")
