-- ============================================================
-- CRM Clínicas — WhatsApp Connections
-- Cada clínica tem o(s) seu(s) próprio(s) número(s) WhatsApp
-- instance_name  = identificador da instância na Evolution API
-- phone_number   = número E.164 visível (informativo)
-- ============================================================

create table whatsapp_connections (
  id            uuid        primary key default uuid_generate_v4(),
  clinica_id    uuid        not null references clinicas(id) on delete cascade,
  instance_name text        not null,   -- único na Evolution API; é a chave de lookup
  phone_number  text        not null,   -- ex: "+351912345678"
  ativo         boolean     not null default true,
  created_at    timestamptz          default now(),

  constraint uq_whatsapp_instance unique (instance_name)
);

-- Lookup principal: recebido no payload do webhook → clinica_id
create index idx_whatsapp_conn_instance on whatsapp_connections(instance_name)
  where ativo = true;

create index idx_whatsapp_conn_clinica  on whatsapp_connections(clinica_id);

-- ─── RLS ─────────────────────────────────────────────────────
-- Clínicas só vêem e gerem as suas próprias conexões.
-- O backend usa a service_key (bypassa RLS) para o lookup no webhook,
-- o que é correcto: o webhook não tem JWT de utilizador.

alter table whatsapp_connections enable row level security;

create policy "clinica_isolada" on whatsapp_connections
  using (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
