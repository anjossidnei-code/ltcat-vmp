# -*- coding: utf-8 -*-
"""Camada de dados do Sistema LTCAT.

Funciona em dois modos:
  * NUVEM (padrao desta pasta) -> grava no Supabase do SMA System, na tabela ltcat_dados,
    SEM chave secreta: usa so a chave publica (a mesma que ja esta dentro do SMA System) e o
    LOGIN do proprio SMA (usuario + senha de administrador). A tabela e fechada (RLS sem politicas);
    todo acesso passa por funcoes do banco (fn_ltcat_*) que conferem usuario e senha.
  * LOCAL -> arquivos JSON na pasta dados\\ (so se LTCAT_MODO=local no ambiente).

Tabela: ltcat_dados(kind text, id text, dados jsonb, atualizado_em timestamptz)
  kind: 'empresa' | 'laudo' | 'config'   (config guarda o signatario, id='signatario')
As logos das empresas ficam dentro do registro da empresa, em dados['logo_b64'] (base64).
Na hora de gerar o PDF, logo_para_arquivo() grava num arquivo temporario, pois o engine.py espera um caminho.
"""
import base64
import glob
import json
import os
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
D_EMP = os.path.join(ROOT, "dados", "empresas")
D_LAUDOS = os.path.join(ROOT, "dados", "laudos")
D_SIG = os.path.join(ROOT, "dados", "signatario.json")

# URL e chave PUBLICA do projeto Supabase do SMA System (as mesmas que ficam no index.html).
# Nao dao acesso a nada sozinhas: a tabela ltcat_dados so responde as funcoes fn_ltcat_*, que exigem login.
_URL_PADRAO = "https://dgjodgdvnhprrktzgaqe.supabase.co"
_KEY_PADRAO = "sb_publishable__C4-aXLmrvXDnLFaOA906Q_iUw2gckJ"


class SemLogin(Exception):
    pass


def _cfg(nome, padrao=""):
    valor = ""
    try:
        import streamlit as st
        valor = st.secrets.get(nome, "") if hasattr(st, "secrets") else ""
    except Exception:
        valor = ""
    return (str(valor or os.environ.get(nome, "") or padrao)).strip()


def modo():
    return "local" if _cfg("LTCAT_MODO").lower() == "local" else "supabase"


def _creds():
    return _cfg("SUPABASE_URL", _URL_PADRAO).rstrip("/"), _cfg("SUPABASE_KEY", _KEY_PADRAO)


# ----------------------------------------------------------------- login (usuario do SMA System)
def _login_atual():
    try:
        import streamlit as st
        return st.session_state.get("_ltcat_user", ""), st.session_state.get("_ltcat_senha", "")
    except Exception:
        return "", ""


def _rpc(nome, payload):
    import requests
    url, key = _creds()
    r = requests.post(url + "/rest/v1/rpc/" + nome, data=json.dumps(payload), timeout=40,
                      headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    if r.status_code >= 400:
        try:
            msg = r.json().get("message") or r.text
        except Exception:
            msg = r.text
        raise RuntimeError(str(msg)[:300])
    return r.json() if r.text else None


def _chamar(nome, **args):
    u, s = _login_atual()
    if not u or not s:
        raise SemLogin("Faça login para continuar.")
    args.update({"p_user": u, "p_senha": s})
    return _rpc(nome, args)


def login(usuario, senha):
    """Confere usuario/senha de administrador do SMA System. Devolve o nome do usuario, ou None se invalido."""
    return _rpc("fn_ltcat_acesso", {"p_user": usuario, "p_senha": senha}) or None


# ----------------------------------------------------------------- utilidades locais
def _jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _jsave(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)


def _dir(kind):
    return D_EMP if kind == "empresa" else D_LAUDOS


# ----------------------------------------------------------------- API
def listar(kind):
    """Devolve dict {id: obj} de todos os registros do tipo (empresa/laudo)."""
    if modo() == "supabase":
        out = {}
        for row in (_chamar("fn_ltcat_listar", p_kind=kind) or []):
            d = row.get("dados") or {}
            d.setdefault("id", row["id"])
            out[row["id"]] = d
        return out
    out = {}
    for p in sorted(glob.glob(os.path.join(_dir(kind), "*.json"))):
        d = _jload(p)
        if d and d.get("id"):
            out[d["id"]] = d
    return out


def obter(kind, id_):
    if modo() == "supabase":
        return _chamar("fn_ltcat_obter", p_kind=kind, p_id=id_)
    return _jload(os.path.join(_dir(kind), id_ + ".json"))


def salvar(kind, id_, obj):
    obj = dict(obj)
    obj["id"] = id_
    if modo() == "supabase":
        _chamar("fn_ltcat_salvar", p_kind=kind, p_id=id_, p_dados=obj)
        return
    _jsave(os.path.join(_dir(kind), id_ + ".json"), obj)


def existe(kind, id_):
    if modo() == "supabase":
        return obter(kind, id_) is not None
    return os.path.exists(os.path.join(_dir(kind), id_ + ".json"))


def excluir(kind, id_):
    if modo() == "supabase":
        _chamar("fn_ltcat_excluir", p_kind=kind, p_id=id_)
        return
    p = os.path.join(_dir(kind), id_ + ".json")
    if os.path.exists(p):
        os.remove(p)


# ----------------------------------------------------------------- signatario (registro unico)
def obter_signatario():
    padrao = {"nome": "", "titulo": "", "crea": ""}
    if modo() == "supabase":
        return obter("config", "signatario") or padrao
    return _jload(D_SIG, padrao)


def salvar_signatario(sig):
    if modo() == "supabase":
        salvar("config", "signatario", sig)
        return
    _jsave(D_SIG, sig)


# ----------------------------------------------------------------- logo
def logo_para_arquivo(emp):
    """Garante que emp['logo'] seja um caminho de arquivo que o engine.py consiga abrir.

    - com logo_b64 no registro: grava num arquivo temporario;
    - senao: mantem o caminho relativo a ROOT (comportamento antigo).
    Devolve o caminho (ou "" se nao houver logo).
    """
    b64 = emp.get("logo_b64")
    if b64:
        try:
            ext = emp.get("logo_ext", "png")
            fd, path = tempfile.mkstemp(suffix="." + ext)
            with os.fdopen(fd, "wb") as fh:
                fh.write(base64.b64decode(b64))
            emp["logo"] = path
            return path
        except Exception:
            emp["logo"] = ""
            return ""
    rel = emp.get("logo")
    if rel:
        path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        if os.path.exists(path):
            emp["logo"] = path
            return path
    emp["logo"] = ""
    return ""


def guardar_logo(emp, nome_arquivo, conteudo):
    """Salva a logo enviada. Na nuvem vai como base64 no proprio registro; no modo local grava na pasta imagens."""
    ext = os.path.splitext(nome_arquivo)[1].lower().lstrip(".") or "png"
    if modo() == "supabase":
        emp["logo_b64"] = base64.b64encode(conteudo).decode()
        emp["logo_ext"] = ext
        emp["logo"] = f"logo_{emp.get('id', 'empresa')}.{ext}"
        return
    nome = f"logo_{emp.get('id', 'empresa')}.{ext}"
    d_img = os.path.join(ROOT, "imagens")
    os.makedirs(d_img, exist_ok=True)
    with open(os.path.join(d_img, nome), "wb") as fh:
        fh.write(conteudo)
    emp["logo"] = f"imagens/{nome}"
