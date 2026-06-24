-- ============================================================
-- CRM Clínicas — Scheduled Jobs audit log
-- Regista cada execução de job agendado: início, resultado,
-- payload de entrada e erro (se aplicável).
-- ============================================================

create table scheduled_jobs (
  id            uuid        primary key default uuid_generate_v4(),
  clinica_id    uuid        references clinicas(id) on delete cascade,
  job_type      text        not null,            -- lembrete_consulta | campanha_retencao | followup_automatico
  status        text        not null default 'running', -- running | success | failed
  payload       jsonb       not null default '{}',      -- job-specific input context
  resultado     jsonb,                           -- output summary (nulls until done)
  iniciado_at   timestamptz not null default now(),
  concluido_at  timestamptz,
  erro          text
);

create index idx_scheduled_jobs_clinica   on scheduled_jobs(clinica_id);
create index idx_scheduled_jobs_tipo      on scheduled_jobs(job_type);
create index idx_scheduled_jobs_status    on scheduled_jobs(status);
create index idx_scheduled_jobs_iniciado  on scheduled_jobs(iniciado_at desc);

-- ─── RLS ─────────────────────────────────────────────────────
-- Clínicas só vêem os seus próprios registos de execução.
-- O scheduler usa service_key e bypassa RLS — correcto para
-- um processo background sem JWT de utilizador.

alter table scheduled_jobs enable row level security;

create policy "clinica_isolada" on scheduled_jobs
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
