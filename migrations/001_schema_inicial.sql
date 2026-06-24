-- ============================================================
-- CRM Clínicas — Schema Supabase
-- Multi-tenant: todas as tabelas têm clinica_id
-- RGPD: consentimento obrigatório, soft delete, auditoria
-- ============================================================

-- Extensão UUID
create extension if not exists "uuid-ossp";

-- ─── CLÍNICAS (tenants) ──────────────────────────────────────
create table clinicas (
  id          uuid primary key default uuid_generate_v4(),
  nome        text not null,
  nif         text,
  email       text,
  telefone    text,
  morada      text,
  cidade      text,
  plano       text default 'starter', -- starter | pro | clinica | enterprise
  ativo       boolean default true,
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- ─── MÉDICOS ─────────────────────────────────────────────────
create table medicos (
  id                      uuid primary key default uuid_generate_v4(),
  clinica_id              uuid references clinicas(id) on delete cascade,
  nome                    text not null,
  especialidade           text not null,
  cedula                  text,
  email                   text,
  telefone                text,
  comissao_pct            numeric(5,2) default 0,
  horarios_disponiveis    jsonb default '{}', -- {seg:["09:00","09:30",...], ter:[...]}
  ativo                   boolean default true,
  created_at              timestamptz default now()
);

-- ─── SALAS ───────────────────────────────────────────────────
create table salas (
  id          uuid primary key default uuid_generate_v4(),
  clinica_id  uuid references clinicas(id) on delete cascade,
  nome        text not null,
  descricao   text,
  ativa       boolean default true
);

-- ─── PACIENTES ───────────────────────────────────────────────
create table pacientes (
  id                      uuid primary key default uuid_generate_v4(),
  clinica_id              uuid references clinicas(id) on delete cascade,
  nome                    text not null,
  telefone                text not null,
  email                   text,
  nif                     text,
  data_nascimento         date,
  genero                  text,
  origem                  text default 'balcao', -- whatsapp|site|indicacao|balcao
  status                  text default 'lead',   -- lead|ativo|inativo|arquivado
  tags                    text[] default '{}',
  notas                   text,
  consentimento_rgpd_at   timestamptz,           -- NULL = sem consentimento ainda
  created_at              timestamptz default now(),
  updated_at              timestamptz default now()
);

create index idx_pacientes_clinica   on pacientes(clinica_id);
create index idx_pacientes_telefone  on pacientes(telefone);
create index idx_pacientes_status    on pacientes(status);
create index idx_pacientes_tags      on pacientes using gin(tags);

-- ─── CONSULTAS ───────────────────────────────────────────────
create table consultas (
  id              uuid primary key default uuid_generate_v4(),
  clinica_id      uuid references clinicas(id) on delete cascade,
  paciente_id     uuid references pacientes(id) on delete cascade,
  medico_id       uuid references medicos(id),
  sala_id         uuid references salas(id),
  data_hora       timestamptz not null,
  duracao_min     integer default 30,
  tipo            text default 'primeira_vez', -- primeira_vez|retorno|urgencia|avaliacao
  status          text default 'agendada',     -- agendada|confirmada|realizada|falta|cancelada
  valor           numeric(10,2),
  forma_pagamento text,
  pago            boolean default false,
  observacoes     text,
  created_at      timestamptz default now()
);

create index idx_consultas_clinica    on consultas(clinica_id);
create index idx_consultas_data_hora  on consultas(data_hora);
create index idx_consultas_paciente   on consultas(paciente_id);
create index idx_consultas_medico     on consultas(medico_id);
create index idx_consultas_status     on consultas(status);

-- ─── PIPELINE ────────────────────────────────────────────────
create table pipeline (
  id                uuid primary key default uuid_generate_v4(),
  clinica_id        uuid references clinicas(id) on delete cascade,
  paciente_id       uuid references pacientes(id) on delete cascade unique,
  etapa             text default 'lead', -- lead|agendou|compareceu|orcamento|tratamento_ativo|concluido
  valor_estimado    numeric(10,2),
  observacoes       text,
  etapa_updated_at  timestamptz default now(),
  created_at        timestamptz default now()
);

create index idx_pipeline_clinica on pipeline(clinica_id);
create index idx_pipeline_etapa   on pipeline(etapa);

-- ─── INTERAÇÕES / TIMELINE ───────────────────────────────────
create table interacoes (
  id          uuid primary key default uuid_generate_v4(),
  clinica_id  uuid references clinicas(id) on delete cascade,
  paciente_id uuid references pacientes(id) on delete cascade,
  tipo        text not null, -- whatsapp|sms|email|ligacao|nota|lembrete|consulta
  direcao     text,          -- entrada|saida
  conteudo    text not null,
  criado_por  text default 'sistema', -- agente_ia|recepcao|sistema
  created_at  timestamptz default now()
);

create index idx_interacoes_paciente  on interacoes(paciente_id);
create index idx_interacoes_clinica   on interacoes(clinica_id);
create index idx_interacoes_created   on interacoes(created_at desc);

-- ─── TRIGGER: updated_at automático ─────────────────────────
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_pacientes_updated_at
  before update on pacientes
  for each row execute function update_updated_at();

create trigger trg_clinicas_updated_at
  before update on clinicas
  for each row execute function update_updated_at();

-- ─── TRIGGER: pipeline automático ao criar paciente ──────────
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

-- ─── RLS (Row Level Security) ────────────────────────────────
-- Cada clínica só vê seus próprios dados

alter table clinicas   enable row level security;
alter table medicos    enable row level security;
alter table salas      enable row level security;
alter table pacientes  enable row level security;
alter table consultas  enable row level security;
alter table pipeline   enable row level security;
alter table interacoes enable row level security;

-- Política base: clinica_id deve bater com o JWT do utilizador
create policy "clinica_isolada" on pacientes
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinica_isolada" on consultas
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinica_isolada" on medicos
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinica_isolada" on salas
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinica_isolada" on pipeline
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

create policy "clinica_isolada" on interacoes
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
