# -*- coding: utf-8 -*-
"""Camada de dados do Sistema LTCAT.

Funciona em dois modos, escolhido automaticamente:
  * SUPABASE  -> quando SUPABASE_URL e SUPABASE_KEY estao definidos
                 (em st.secrets ou nas variaveis de ambiente). Usado na nuvem.
  * LOCAL     -> caso contrario: le/grava arquivos JSON na pasta dados\
                 (comportamento original, para rodar no PC).

Guarda tudo numa unica tabela no Supabase:
    ltcat_dados(kind text, id text, dados jsonb, atualizado_em timestamptz)
  kind: 'empresa' | 'laudo' | 'config'
  config guarda o signatario (id='signatario').
As logos das empresas ficam dentro do proprio registro da empresa, em
dados['logo_b64'] (imagem em base64). Na hora de gerar o PDF, logo_para_arquivo()
grava num arquivo temporario, pois o engine.py espera um caminho de arquivo.
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
TABELA = "ltcat_dados"

_client = None
_mode = None


def _creds():
    url = key = ""
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "") if hasattr(st, "secrets") else ""
        key = st.secrets.get("SUPABASE_KEY", "") if hasattr(st, "secrets") else ""
    except Exception:
        pass
    url = url or os.environ.get("SUPABASE_URL", "")
    key = key or os.environ.get("SUPABASE_KEY", "")
    return url.strip(), key.strip()


def _init():
    global _client, _mode
    if _mode is not None:
        return
    url, key = _creds()
    if url and key:
        try:
            from supabase import create_client
            _client = create_client(url, key)
            _mode = "supabase"
            return
        except Exception as e:
            print("Supabase indisponivel, usando modo local:", e)
    _mode = "local"


def modo():
    _init()
    return _mode


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
    _init()
    if _mode == "supabase":
        r = _client.table(TABELA).select("id,dados").eq("kind", kind).execute()
        out = {}
        for row in (r.data or []):
            d = row["dados"] or {}
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
    _init()
    if _mode == "supabase":
        r = _client.table(TABELA).select("dados").eq("kind", kind).eq("id", id_).limit(1).execute()
        if r.data:
            return r.data[0]["dados"]
        return None
    return _jload(os.path.join(_dir(kind), id_ + ".json"))


def salvar(kind, id_, obj):
    _init()
    obj = dict(obj)
    obj["id"] = id_
    if _mode == "supabase":
        _client.table(TABELA).upsert({"kind": kind, "id": id_, "dados": obj}).execute()
        return
    _jsave(os.path.join(_dir(kind), id_ + ".json"), obj)


def existe(kind, id_):
    _init()
    if _mode == "supabase":
        r = _client.table(TABELA).select("id").eq("kind", kind).eq("id", id_).limit(1).execute()
        return bool(r.data)
    return os.path.exists(os.path.join(_dir(kind), id_ + ".json"))


def excluir(kind, id_):
    _init()
    if _mode == "supabase":
        _client.table(TABELA).delete().eq("kind", kind).eq("id", id_).execute()
        return
    p = os.path.join(_dir(kind), id_ + ".json")
    if os.path.exists(p):
        os.remove(p)


# ----------------------------------------------------------------- signatario (registro unico)
def obter_signatario():
    _init()
    padrao = {"nome": "", "titulo": "", "crea": ""}
    if _mode == "supabase":
        return obter("config", "signatario") or padrao
    return _jload(D_SIG, padrao)


def salvar_signatario(sig):
    _init()
    if _mode == "supabase":
        salvar("config", "signatario", sig)
        return
    _jsave(D_SIG, sig)


# ----------------------------------------------------------------- logo
def logo_para_arquivo(emp):
    """Garante que emp['logo'] seja um caminho de arquivo que o engine.py consiga abrir.

    - modo supabase: a logo vem em emp['logo_b64']; grava num arquivo temporario.
    - modo local: mantem o caminho relativo a ROOT (comportamento antigo).
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
    """Salva a logo enviada. No modo supabase vai como base64 no proprio registro;
    no modo local grava na pasta imagens (comportamento antigo)."""
    _init()
    ext = os.path.splitext(nome_arquivo)[1].lower().lstrip(".") or "png"
    if _mode == "supabase":
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
