import json
import glob
import os
import re

# Campos obrigatórios do schema v3
REQUIRED_FIELDS_V3 = [
    "id", "lei", "versao", "versao_consolidada", "artigo",
    "texto_limpo", "status", "hash_artigo", "url_fonte", "data_extracao",
]

VALID_STATUS = {"vigente", "vetado_total", "revogado"}


def eh_arquivo_de_lei(nome: str) -> bool:
    """True so para os JSONs de ARTIGOS ({lei}_{data}.json). Exclui hashes.json,
    perguntas e o sidecar _riscadas.json (historico de redacoes — schema proprio,
    2026-07-08: os 13 'erros' fantasmas vinham de tentar le-lo como artigos)."""
    return (nome.endswith(".json")
            and not nome.startswith("hashes")
            and "_questions" not in nome
            and "_riscadas" not in nome)


def verificar_integridade():
    print("Auditoria de Integridade Justina RAG (v3)\n")

    arquivos_json = sorted(glob.glob("data/*.json"))
    arquivos_json = [f for f in arquivos_json if eh_arquivo_de_lei(os.path.basename(f))]

    if not arquivos_json:
        print("Nenhum arquivo JSON encontrado na pasta data/.")
        return

    resumo_geral = []
    total_erros = 0

    for json_path in arquivos_json:
        base_name = os.path.basename(json_path)
        print(f"--- {base_name} ---")
        erros_arquivo = 0

        # 1. Auditoria de Arquivos Fisicos
        clean_path = json_path.replace(".json", "_clean.txt")
        if not os.path.exists(clean_path):
            print("  [WARN] Arquivo _clean.txt nao encontrado.")

        # 2. Auditoria de Conteudo JSON
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)

            if not dados:
                print("  [FAIL] JSON vazio.")
                total_erros += 1
                continue

            # Campos obrigatorios v3
            for i, item in enumerate(dados):
                missing = [f for f in REQUIRED_FIELDS_V3 if f not in item]
                if missing:
                    art = item.get("artigo", f"chunk[{i}]")
                    print(f"  [FAIL] {art}: campos faltando: {missing}")
                    erros_arquivo += 1

            # Verificacao de Duplicados (por ID)
            ids = [item.get("id", "") for item in dados]
            duplicados = set(x for x in ids if ids.count(x) > 1)

            # Verificacao de HTML residual
            amostra_texto = " ".join(item.get("texto_limpo", "") for item in dados[:5])
            tem_html = bool(re.search(r'<(html|body|div|script|style)\b', amostra_texto, re.IGNORECASE))

            # Verificacao de status validos
            status_invalidos = [
                item.get("artigo", "?")
                for item in dados
                if item.get("status", "") not in VALID_STATUS
            ]

            # Consistencia de lei/versao
            leis = set(item.get("lei", "") for item in dados)
            if len(leis) > 1:
                print(f"  [FAIL] Multiplas siglas no mesmo arquivo: {leis}")
                erros_arquivo += 1

            if tem_html:
                print("  [FAIL] Detectado HTML residual no conteudo.")
                erros_arquivo += 1
            if duplicados:
                print(f"  [FAIL] IDs duplicados: {sorted(duplicados)[:5]}")
                erros_arquivo += 1
            if status_invalidos:
                print(f"  [WARN] Status invalido em: {status_invalidos[:3]}")

            # Distribuicao de status
            vigentes = sum(1 for item in dados if item.get("status") == "vigente")
            vetados = sum(1 for item in dados if item.get("status") == "vetado_total")
            revogados = sum(1 for item in dados if item.get("status") == "revogado")

            if erros_arquivo == 0:
                lei = dados[0].get("lei", "?")
                print(f"  [OK] {len(dados)} blocos | vigentes={vigentes} vetados={vetados} revogados={revogados}")
                resumo_geral.append(
                    f"{base_name:40} | {len(dados):4} blocos | "
                    f"V={vigentes} T={vetados} R={revogados} | lei={lei}"
                )

            total_erros += erros_arquivo

        except Exception as e:
            print(f"  [FAIL] Erro ao processar JSON: {e}")
            total_erros += 1
        print("")

    print("RESUMO DA BASE DE CONHECIMENTO:")
    print("-" * 80)
    for r in resumo_geral:
        print(r)
    print("-" * 80)
    print(f"\nTotal de erros: {total_erros}")

    return total_erros == 0


if __name__ == "__main__":
    ok = verificar_integridade()
    exit(0 if ok else 1)
