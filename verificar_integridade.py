import json
import glob
import os
import re

def verificar_integridade():
    print("🛡️ Auditoria de Integridade Justina RAG\n")
    
    arquivos_json = glob.glob("data/*.json")
    if not arquivos_json:
        print("❌ Nenhum arquivo JSON encontrado na pasta data/.")
        return

    resumo_geral = []

    for json_path in arquivos_json:
        base_name = os.path.basename(json_path)
        print(f"--- ⚖️ {base_name} ---")
        
        # 1. Auditoria de Arquivos Físicos
        clean_path = json_path.replace(".json", "_clean.txt")
        if not os.path.exists(clean_path):
            print("  ❌ Erro: Arquivo _clean.txt não encontrado.")
        
        # 2. Auditoria de Conteúdo JSON
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            if not dados:
                print("  ❌ Erro: JSON vazio.")
                continue

            # Verificação de Duplicados
            artigos = [item['artigo'] for item in dados]
            duplicados = set([x for x in artigos if artigos.count(x) > 1 and x != 'EMENTA'])
            
            # Verificação de HTML residual
            amostra_texto = " ".join([item['texto'] for item in dados[:5]])
            tem_html = "<html" in amostra_texto.lower() or "<body" in amostra_texto.lower()
            
            # Verificação de Prefixo de Contexto
            prefixo_ok = all(item['texto'].startswith(f"[{item['lei']}]") for item in dados)

            if tem_html: print("  ❌ Erro: Detectado lixo HTML no conteúdo.")
            if duplicados: print(f"  ❌ Erro: Artigos duplicados encontrados: {list(duplicados)[:3]}...")
            if not prefixo_ok: print("  ⚠️ Aviso: Alguns blocos estão sem o prefixo [SIGLA].")
            
            if not tem_html and not duplicados and prefixo_ok:
                print(f"  ✅ Integridade confirmada: {len(dados)} blocos estruturados.")
                ementa_preview = dados[0]['texto'][:80].replace('\n', ' ')
                resumo_geral.append(f"{base_name:30} | {len(dados):4} blocos | Ementa: {ementa_preview}...")

        except Exception as e:
            print(f"  💥 Erro crítico ao processar JSON: {e}")
        print("")

    print("📊 RESUMO DA BASE DE CONHECIMENTO:")
    print("-" * 80)
    for r in resumo_geral:
        print(r)
    print("-" * 80)

if __name__ == "__main__":
    verificar_integridade()
