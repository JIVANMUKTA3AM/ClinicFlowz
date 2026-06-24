-- ============================================================
-- ClinicFlowz — setup_completo.sql
-- Script único para criar o banco do zero num projecto Supabase
-- novo e vazio.  Multi-tenant com RLS COMPLETO (SELECT + INSERT
-- + UPDATE + DELETE) em todas as 9 tabelas.
--
-- Aplicar via: Supabase Dashboard → SQL Editor → Run
-- (ou psql -f setup_completo.sql)
-- ============================================================


-- ============================================================
-- EXTENSÃO
-- ============================================================

create extension if not exists "uuid-ossp";   -- uuid_generate_v4() usado por todas as PKs


-- ============================================================
-- TABELAS
-- Ordem de criação respeita dependências FK:
--   clinicas (nenhuma FK)
--   medicos, salas  → clinicas
--   pacientes       → clinicas
--   consultas       → clinicas, pacientes, medicos, salas
--   pipeline        → clinicas, pacientes
--   interacoes      → clinicas, pacientes
--   whatsapp_connections → clinicas
--   scheduled_jobs  → clinicas
-- ============================================================

-- ─── 1. CLÍNICAS (tenant root) ───────────────────────────────────────────────
create table clinicas (
  id          uuid        primary key default uuid_generate_v4(),
  nome        text        not null,
  nif         text,
  email       text,
  telefone    text,
  morada      text,
  cidade      text,
  plano       text        default 'starter', -- starter | pro | clinica | enterprise
  ativo       boolean     default true,
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- ─── 2. MÉDICOS ──────────────────────────────────────────────────────────────
create table medicos (
  id                   uuid        primary key default uuid_generate_v4(),
  clinica_id           uuid        references clinicas(id) on delete cascade,
  nome                 text        not null,
  especialidade        text        not null,
  cedula               text,
  email                text,
  telefone             text,
  comissao_pct         numeric(5,2) default 0,
  horarios_disponiveis jsonb        default '{}', -- {seg:["09:00","09:30",...], ter:[...]}
  ativo                boolean     default true,
  created_at           timestamptz default now()
);

-- ─── 3. SALAS ────────────────────────────────────────────────────────────────
create table salas (
  id          uuid        primary key default uuid_generate_v4(),
  clinica_id  uuid        references clinicas(id) on delete cascade,
  nome        text        not null,
  descricao   text,
  ativa       boolean     default true
);

-- ─── 4. PACIENTES ────────────────────────────────────────────────────────────
create table pacientes (
  id                    uuid        primary key default uuid_generate_v4(),
  clinica_id            uuid        references clinicas(id) on delete cascade,
  nome                  text        not null,
  telefone              text        not null,
  email                 text,
  nif                   text,
  data_nascimento       date,
  genero                text,
  origem                text        default 'balcao', -- whatsapp|site|indicacao|balcao
  status                text        default 'lead',   -- lead|ativo|inativo|arquivado
  tags                  text[]      default '{}',
  notas                 text,
  consentimento_rgpd_at timestamptz,                  -- NULL = sem consentimento ainda
  created_at            timestamptz default now(),
  updated_at            timestamptz default now()
);

create index idx_pacientes_clinica  on pacientes(clinica_id);
create index idx_pacientes_telefone on pacientes(telefone);
create index idx_pacientes_status   on pacientes(status);
create index idx_pacientes_tags     on pacientes using gin(tags);

-- ─── 5. CONSULTAS ────────────────────────────────────────────────────────────
-- Todas as FK subordinadas (pacientes, medicos, salas) já existem neste ponto
create table consultas (
  id              uuid        primary key default uuid_generate_v4(),
  clinica_id      uuid        references clinicas(id)  on delete cascade,
  paciente_id     uuid        references pacientes(id) on delete cascade,
  medico_id       uuid        references medicos(id),
  sala_id         uuid        references salas(id),
  data_hora       timestamptz not null,
  duracao_min     integer     default 30,
  tipo            text        default 'primeira_vez', -- primeira_vez|retorno|urgencia|avaliacao
  status          text        default 'agendada',     -- agendada|confirmada|realizada|falta|cancelada
  valor           numeric(10,2),
  forma_pagamento text,
  pago            boolean     default false,
  observacoes     text,
  created_at      timestamptz default now()
);

create index idx_consultas_clinica   on consultas(clinica_id);
create index idx_consultas_data_hora on consultas(data_hora);
create index idx_consultas_paciente  on consultas(paciente_id);
create index idx_consultas_medico    on consultas(medico_id);
create index idx_consultas_status    on consultas(status);

-- ─── 6. PIPELINE ─────────────────────────────────────────────────────────────
create table pipeline (
  id               uuid        primary key default uuid_generate_v4(),
  clinica_id       uuid        references clinicas(id)  on delete cascade,
  paciente_id      uuid        references pacientes(id) on delete cascade unique,
  etapa            text        default 'lead', -- lead|agendou|compareceu|orcamento|tratamento_ativo|concluido
  valor_estimado   numeric(10,2),
  observacoes      text,
  etapa_updated_at timestamptz default now(),
  created_at       timestamptz default now()
);

create index idx_pipeline_clinica on pipeline(clinica_id);
create index idx_pipeline_etapa   on pipeline(etapa);

-- ─── 7. INTERAÇÕES / TIMELINE ────────────────────────────────────────────────
create table interacoes (
  id          uuid        primary key default uuid_generate_v4(),
  clinica_id  uuid        references clinicas(id)  on delete cascade,
  paciente_id uuid        references pacientes(id) on delete cascade,
  tipo        text        not null, -- whatsapp|sms|email|ligacao|nota|lembrete|consulta
  direcao     text,                 -- entrada|saida
  conteudo    text        not null,
  criado_por  text        default 'sistema', -- agente_ia|recepcao|sistema
  created_at  timestamptz default now()
);

create index idx_interacoes_paciente on interacoes(paciente_id);
create index idx_interacoes_clinica  on interacoes(clinica_id);
create index idx_interacoes_created  on interacoes(created_at desc);

-- ─── 8. WHATSAPP CONNECTIONS ─────────────────────────────────────────────────
create table whatsapp_connections (
  id            uuid        primary key default uuid_generate_v4(),
  clinica_id    uuid        not null references clinicas(id) on delete cascade,
  instance_name text        not null,   -- único na Evolution API; chave de lookup
  phone_number  text        not null,   -- ex: "+351912345678"
  ativo         boolean     not null default true,
  created_at    timestamptz          default now(),

  constraint uq_whatsapp_instance unique (instance_name)
);

-- Lookup principal: payload do webhook → clinica_id
create index idx_whatsapp_conn_instance on whatsapp_connections(instance_name) where ativo = true;
create index idx_whatsapp_conn_clinica  on whatsapp_connections(clinica_id);

-- ─── 9. SCHEDULED JOBS ───────────────────────────────────────────────────────
create table scheduled_jobs (
  id           uuid        primary key default uuid_generate_v4(),
  clinica_id   uuid        references clinicas(id) on delete cascade,
  job_type     text        not null,            -- lembrete_consulta|campanha_retencao|followup_automatico
  status       text        not null default 'running', -- running|success|failed
  payload      jsonb       not null default '{}',
  resultado    jsonb,
  iniciado_at  timestamptz not null default now(),
  concluido_at timestamptz,
  erro         text
);

create index idx_scheduled_jobs_clinica  on scheduled_jobs(clinica_id);
create index idx_scheduled_jobs_tipo     on scheduled_jobs(job_type);
create index idx_scheduled_jobs_status   on scheduled_jobs(status);
create index idx_scheduled_jobs_iniciado on scheduled_jobs(iniciado_at desc);


-- ============================================================
-- FUNÇÕES E TRIGGERS
-- (declarados depois de todas as tabelas para evitar erros de
--  referência a tabelas ainda não existentes)
-- ============================================================

-- Trigger: updated_at automático em clinicas e pacientes
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_clinicas_updated_at
  before update on clinicas
  for each row execute function update_updated_at();

create trigger trg_pacientes_updated_at
  before update on pacientes
  for each row execute function update_updated_at();

-- Trigger: cria entrada no pipeline automaticamente ao inserir paciente
create or replace function criar_pipeline_para_paciente()
returns trigger as $$
begin
  insert into pipeline (clinica_id, paciente_id, etapa)
  values (new.clinica_id, new.id, 'lead');
  return new;
end;
$$ language plpgsql;

create trigger trg_pipeline_on_paciente
  after insert on pacientes
  for each row execute function criar_pipeline_para_paciente();


-- ============================================================
-- ROW LEVEL SECURITY — habilitar em todas as tabelas
-- ============================================================

alter table clinicas             enable row level security;
alter table medicos              enable row level security;
alter table salas                enable row level security;
alter table pacientes            enable row level security;
alter table consultas            enable row level security;
alter table pipeline             enable row level security;
alter table interacoes           enable row level security;
alter table whatsapp_connections enable row level security;
alter table scheduled_jobs       enable row level security;


-- ============================================================
-- POLICIES RLS — 4 operações × 9 tabelas
--
-- Path JWT em todas as policies (excepto clinicas):
--   clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid
--
-- Tabela clinicas (tenant root):
--   id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid
--
-- Nota sobre o backend FastAPI: usa service_role key (bypassa RLS).
-- As policies protegem acesso directo via anon key / JWTs de utilizadores.
-- ============================================================


-- ─── 1. clinicas ─────────────────────────────────────────────────────────────
-- Cada utilizador vê e edita apenas a sua própria clínica.
-- INSERT e DELETE são bloqueados via JWT; o backend usa service key para
-- criar e (eventualmente) eliminar tenants.

create policy "clinicas_select" on clinicas
  for select
  using (id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinicas_insert" on clinicas
  for insert
  with check (false);
  -- Criação de tenant apenas pelo backend (service key bypassa esta policy).
  -- Bloqueia qualquer tentativa de INSERT via anon/JWT directo.

create policy "clinicas_update" on clinicas
  for update
  using      (id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinicas_delete" on clinicas
  for delete
  using (false);
  -- Eliminação de tenant apenas via service key; bloqueia JWT directo.


-- ─── 2. medicos ──────────────────────────────────────────────────────────────

create policy "medicos_select" on medicos
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "medicos_insert" on medicos
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "medicos_update" on medicos
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "medicos_delete" on medicos
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 3. salas ────────────────────────────────────────────────────────────────

create policy "salas_select" on salas
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "salas_insert" on salas
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "salas_update" on salas
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "salas_delete" on salas
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 4. pacientes ────────────────────────────────────────────────────────────

create policy "pacientes_select" on pacientes
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "pacientes_insert" on pacientes
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "pacientes_update" on pacientes
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "pacientes_delete" on pacientes
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 5. consultas ────────────────────────────────────────────────────────────

create policy "consultas_select" on consultas
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "consultas_insert" on consultas
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "consultas_update" on consultas
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "consultas_delete" on consultas
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 6. pipeline ─────────────────────────────────────────────────────────────

create policy "pipeline_select" on pipeline
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "pipeline_insert" on pipeline
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "pipeline_update" on pipeline
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "pipeline_delete" on pipeline
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 7. interacoes ───────────────────────────────────────────────────────────

create policy "interacoes_select" on interacoes
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "interacoes_insert" on interacoes
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "interacoes_update" on interacoes
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "interacoes_delete" on interacoes
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 8. whatsapp_connections ─────────────────────────────────────────────────

create policy "whatsapp_connections_select" on whatsapp_connections
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "whatsapp_connections_insert" on whatsapp_connections
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "whatsapp_connections_update" on whatsapp_connections
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "whatsapp_connections_delete" on whatsapp_connections
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ─── 9. scheduled_jobs ───────────────────────────────────────────────────────
-- O scheduler corre com service key (bypassa RLS).
-- Policies protegem leitura/escrita directa via JWT de utilizador.

create policy "scheduled_jobs_select" on scheduled_jobs
  for select
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "scheduled_jobs_insert" on scheduled_jobs
  for insert
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "scheduled_jobs_update" on scheduled_jobs
  for update
  using      (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid)
  with check (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "scheduled_jobs_delete" on scheduled_jobs
  for delete
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);


-- ============================================================
-- AUDITORIA DE POLICIES
-- ============================================================
/*
  Tabela                | SELECT | INSERT      | UPDATE | DELETE      | Obs
  ──────────────────────────────────────────────────────────────────────────────────────────
  clinicas              |   ✓    |  ✓ (false)  |   ✓    |  ✓ (false)  | tenant root; usa id= em vez de clinica_id=; INSERT/DELETE bloqueados via JWT (service key bypassa)
  medicos               |   ✓    |  ✓          |   ✓    |  ✓          |
  salas                 |   ✓    |  ✓          |   ✓    |  ✓          |
  pacientes             |   ✓    |  ✓          |   ✓    |  ✓          |
  consultas             |   ✓    |  ✓          |   ✓    |  ✓          |
  pipeline              |   ✓    |  ✓          |   ✓    |  ✓          |
  interacoes            |   ✓    |  ✓          |   ✓    |  ✓          |
  whatsapp_connections  |   ✓    |  ✓          |   ✓    |  ✓          |
  scheduled_jobs        |   ✓    |  ✓          |   ✓    |  ✓          |

  Operações ADICIONADAS vs. migrações originais (001/002/003):
  ─────────────────────────────────────────────────────────────
  • 001 usava "create policy ... USING (...)" sem cláusula FOR:
      - Cobria todas as ops implicitamente, mas WITH CHECK era
        igual ao USING (não explícito para INSERT/UPDATE).
      - clinicas: NÃO tinha policy nenhuma (lacuna detectada).
  • 002/003: mesmo padrão — USING sem FOR, sem WITH CHECK explícito.

  Este script substitui todas as policies originais por 4 policies
  explícitas (FOR SELECT / INSERT / UPDATE / DELETE) com WITH CHECK
  diferenciado em INSERT e UPDATE, garantindo que nenhuma linha
  pode ser gravada com clinica_id de outro tenant.

  Path JWT (igual em todas as 9 tabelas, excepto clinicas):
    (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid
*/
