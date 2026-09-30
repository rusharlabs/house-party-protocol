[English](HOOK-SKILL-STANDARDS.md) · [Português](HOOK-SKILL-STANDARDS.pt-BR.md)

# HOOK, SKILL, MCP AND SUB-AGENT STANDARDS

> **Version:** 1.0.0
> **Created:** 2026-01-14
> **Status:** ACTIVE
> **Purpose:** Central reference for this kit's hook, skill, MCP and sub-agent conventions

---

## OVERVIEW

This document defines the MANDATORY rules for Claude Code extensions in this kit. Every creation or modification of hooks, skills, MCP configs, or SDK sub-agents MUST follow these rules.

---

## 1. RULES FOR HOOKS

### 1.1 Mandatory Timeout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  REGRA: Todo hook DEVE ter "timeout": 30                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ✅ CORRETO:                                                                 │
│  {                                                                           │
│    "type": "command",                                                        │
│    "command": "python3 'script.py'",                                         │
│    "timeout": 30                                                             │
│  }                                                                           │
│                                                                              │
│  ❌ INCORRETO:                                                               │
│  {                                                                           │
│    "type": "command",                                                        │
│    "command": "python3 'script.py'"                                          │
│  }                                                                           │
│                                                                              │
│  MOTIVO: Previne hang do CLI se hook travar                                  │
│  VALOR: 30 segundos (padrão deste kit)                                       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Error Handling (Exit Codes)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  REGRA: Usar exit codes apropriados, NÃO suprimir erros                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  EXIT CODES:                                                                 │
│  ├── 0 = Sucesso (hook passou)                                               │
│  ├── 1 = Aviso (continua mas notifica)                                       │
│  └── 2 = Erro/Bloqueio (para execução)                                       │
│                                                                              │
│  ❌ EVITAR (padrão problemático):                                            │
│  "command": "script.py 2>/dev/null || true"                                  │
│                                                                              │
│  ✅ PREFERIR (tratamento adequado):                                          │
│  try:                                                                        │
│      # código                                                                │
│      sys.exit(0)  # sucesso                                                  │
│  except NonCriticalError:                                                    │
│      print(json.dumps({"warning": str(e)}))                                  │
│      sys.exit(1)  # aviso                                                    │
│  except CriticalError:                                                       │
│      print(json.dumps({"error": str(e)}))                                    │
│      sys.exit(2)  # bloqueio                                                 │
│                                                                              │
│  NOTA: 2>/dev/null || true pode ocultar bugs críticos                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Hook Structure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ESTRUTURA OBRIGATÓRIA DE HOOK:                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  {                                                                           │
│    "type": "command",           // OBRIGATÓRIO                               │
│    "command": "...",            // OBRIGATÓRIO                               │
│    "timeout": 30                // OBRIGATÓRIO (esta regra)                  │
│  }                                                                           │
│                                                                              │
│  LIFECYCLE EVENTS DISPONÍVEIS:                                               │
│  ├── PreToolUse      → Antes de executar ferramenta                          │
│  ├── PostToolUse     → Após executar ferramenta                              │
│  ├── UserPromptSubmit→ Quando usuário envia mensagem                         │
│  ├── SessionStart    → Início de sessão                                      │
│  ├── Stop            → Fim de sessão                                         │
│  ├── Notification    → Eventos de notificação                                │
│  └── SubagentStop    → Quando sub-agente termina                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. RULES FOR SKILLS

### 2.1 Mandatory Header

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  REGRA: Todo SKILL.md DEVE ter header padronizado                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  HEADER OBRIGATÓRIO (primeiras lines):                                      │
│                                                                              │
│  > **Auto-Trigger:** [Quando ativar automaticamente]                         │
│  > **Keywords:** "keyword1", "keyword2", "keyword3"                          │
│  > **Prioridade:** [ALTA | MÉDIA | BAIXA]                                    │
│  > **Tools:** [Lista de tools que a skill usa]                               │
│                                                                              │
│  SEÇÃO OBRIGATÓRIA "Quando NÃO Ativar":                                      │
│                                                                              │
│  ## Quando NÃO Ativar                                                        │
│  - [Situação 1 onde NÃO usar]                                                │
│  - [Situação 2 onde NÃO usar]                                                │
│                                                                              │
│  MOTIVO: Header legível por máquina permite roteamento por keyword           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Skill Structure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ESTRUTURA DE DIRETÓRIO:                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  /.claude/skills/                                                            │
│  └── [nome-da-skill]/                                                        │
│      ├── SKILL.md           ← Instruções (OBRIGATÓRIO)                       │
│      ├── README.md          ← Documentação (opcional)                        │
│      └── [recursos]/        ← Scripts, templates (opcional)                  │
│                                                                              │
│  SEÇÕES OBRIGATÓRIAS NO SKILL.md:                                            │
│  1. Header com Auto-Trigger, Keywords, Prioridade, Tools                     │
│  2. Descrição do propósito                                                   │
│  3. Instruções de uso                                                        │
│  4. "Quando NÃO Ativar"                                                      │
│  5. Exemplos de uso                                                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. RULES FOR MCP (Model Context Protocol)

### 3.1 Secure Credentials

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  REGRA: NUNCA tokens em plaintext em configurações                           │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ❌ PROIBIDO (exposição de credenciais):                                     │
│  "env": {                                                                    │
│    "API_KEY": "sk-1234567890abcdef..."                                       │
│  }                                                                           │
│                                                                              │
│  ✅ CORRETO (variáveis de ambiente):                                         │
│  "env": {}                                                                   │
│                                                                              │
│  Com credenciais em ~/.zshrc ou ~/.bashrc:                                   │
│  export API_KEY="sk-1234567890abcdef..."                                     │
│                                                                              │
│  CREDENCIAIS SENSÍVEIS:                                                      │
│  ├── API keys (provedores de LLM, plataformas de automação, etc.)            │
│  ├── Tokens de acesso (OAuth, serviços de voz e transcrição, etc.)           │
│  ├── Secrets e passwords                                                     │
│  └── Qualquer string que dê acesso a recursos                                │
│                                                                              │
│  MOTIVO: settings.local.json pode ser commitado ou vazado                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 MCP Server Structure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ESTRUTURA PADRÃO:                                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  "mcpServers": {                                                             │
│    "nome-do-servidor": {                                                     │
│      "command": "npx",          // ou caminho do executável                  │
│      "args": [                                                               │
│        "-y",                                                                 │
│        "@org/mcp-server-name"                                                │
│      ],                                                                      │
│      "env": {}                  // VAZIO - usar env vars do shell            │
│    }                                                                         │
│  }                                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. RULES FOR SDK SUB-AGENTS

### 4.1 Principle of Least Privilege

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  REGRA: Sub-agents DEVEM ter allowedTools e maxTurns explícitos              │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CONFIGURAÇÕES OBRIGATÓRIAS:                                                 │
│  {                                                                           │
│    "allowedTools": ["Tool1", "Tool2"],  // Lista explícita                   │
│    "maxTurns": 15                        // Limite de iterações              │
│  }                                                                           │
│                                                                              │
│  NÍVEIS DE ACESSO RECOMENDADOS:                                              │
│                                                                              │
│  ANALYZER (leitura apenas):                                                  │
│  allowedTools: ["Read", "Glob", "Grep"]                                      │
│  maxTurns: 15                                                                │
│                                                                              │
│  RESEARCHER (leitura + web):                                                 │
│  allowedTools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]             │
│  maxTurns: 20                                                                │
│                                                                              │
│  WRITER (leitura + escrita):                                                 │
│  allowedTools: ["Read", "Glob", "Grep", "Write", "Edit"]                     │
│  maxTurns: 25                                                                │
│                                                                              │
│  EXECUTOR (leitura + escrita + bash):                                        │
│  allowedTools: ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]             │
│  maxTurns: 30                                                                │
│                                                                              │
│  ❌ NUNCA:                                                                   │
│  allowedTools: ["*"]  // Acesso total é proibido                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Sub-Agent Structure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  LOCALIZAÇÃO E ESTRUTURA:                                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SDK sub-agents sao configurados via Claude Agent SDK,                        │
│  NAO via diretorio local. Ver documentacao Anthropic.                         │
│                                                                              │
│  HEADER OBRIGATÓRIO NO AGENT.md:                                             │
│                                                                              │
│  > **Auto-Trigger:** [Quando ativar]                                         │
│  > **Keywords:** "keyword1", "keyword2"                                      │
│  > **Prioridade:** [ALTA | MÉDIA | BAIXA]                                    │
│  > **allowedTools:** ["Tool1", "Tool2"]                                      │
│  > **maxTurns:** [número]                                                    │
│                                                                              │
│  NOTA: Sub-agents são delegados pelo orquestrador principal, diferentes de   │
│        agentes de conhecimento usados em deliberação multi-agente           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. RULES FOR PERMISSIONS

### 5.1 Mandatory Deny List

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  REGRA: Configurar deny list para comandos perigosos                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DENY LIST MÍNIMA OBRIGATÓRIA:                                               │
│                                                                              │
│  "deny": [                                                                   │
│    // Comandos destrutivos                                                   │
│    "Bash(rm:-rf *)",                                                         │
│    "Bash(rm:* -rf *)",                                                       │
│                                                                              │
│    // Downloads externos (risco de código malicioso)                         │
│    "Bash(curl:*)",                                                           │
│    "Bash(wget:*)",                                                           │
│                                                                              │
│    // Arquivos sensíveis - SSH                                               │
│    "Read(~/.ssh/*)",                                                         │
│    "Write(~/.ssh/*)",                                                        │
│    "Edit(~/.ssh/*)",                                                         │
│                                                                              │
│    // Arquivos sensíveis - Environment                                       │
│    "Read(*.env)",                                                            │
│    "Write(*.env)",                                                           │
│    "Edit(*.env)",                                                            │
│    "Read(*/.env)",                                                           │
│    "Write(*/.env)",                                                          │
│    "Edit(*/.env)"                                                            │
│  ]                                                                           │
│                                                                              │
│  MOTIVO: Protege contra execução acidental de comandos perigosos             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. VALIDATION CHECKLIST

### 6.1 When Creating a Hook

```
[ ] Tem "timeout": 30?
[ ] Error handling com exit codes (0, 1, 2)?
[ ] Evita 2>/dev/null || true?
[ ] Registrado em settings.local.json?
[ ] Testado isoladamente?
```

### 6.2 When Creating a Skill

```
[ ] Header com Auto-Trigger, Keywords, Prioridade, Tools?
[ ] Seção "Quando NÃO Ativar"?
[ ] Estrutura de diretório correta?
[ ] Instruções claras de uso?
[ ] Exemplos incluídos?
```

### 6.3 When Creating/Modifying an MCP Config

```
[ ] Nenhum token em plaintext?
[ ] Credenciais em variáveis de ambiente?
[ ] env: {} vazio no settings.local.json?
[ ] ~/.zshrc atualizado com exports?
```

### 6.4 When Creating a Sub-Agent

```
[ ] allowedTools explícito (não ["*"])?
[ ] maxTurns definido?
[ ] Header com Keywords para auto-routing?
[ ] AGENT.md + SOUL.md presentes?
[ ] Segue padrao SDK se aplicavel?
```

---

## 7. REFERENCES

- **Claude Code docs (hook, settings and sub-agent schema):** https://docs.anthropic.com/claude-code
- **Hook Lifecycle:** settings.local.json → hooks
- **MCP Protocol:** https://modelcontextprotocol.io

---

## 8. HOW TO APPLY

This kit ships no automatic validator for these rules. Apply them with the checklist in section 6 whenever you create or change a hook, skill, MCP config or sub-agent.

Nothing here blocks automatically: if you want enforcement, wire your own PreToolUse check that warns (exit 1) on a violation, following section 1.2.

---

**END OF DOCUMENT**

