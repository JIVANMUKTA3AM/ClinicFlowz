-- ============================================================
-- Seed — Base de Conhecimento: Clínica Estética Exemplo
--
-- Substitui :TENANT_ID pelo UUID real da clínica antes de executar:
--   psql ... -v TENANT_ID="'uuid-aqui'"
-- Ou executa via endpoint POST /api/kb/seed após autenticação.
--
-- Embeddings são NULL — gerados automaticamente quando o
-- endpoint PUT /api/kb/{id} é chamado ou via /api/kb/reembed-all.
-- Enquanto sem embedding, a busca usa fallback por keywords (ILIKE).
-- ============================================================

-- ─── EMPRESA ─────────────────────────────────────────────────

INSERT INTO wa_kb_entities (tenant_id, category, title, content, metadata) VALUES
(:TENANT_ID, 'empresa', 'Sobre a clínica',
'Somos uma clínica de medicina estética focada em procedimentos minimamente invasivos seguros e naturais.
Nosso objetivo é realçar a beleza natural de cada paciente, respeitando a individualidade e promovendo autoestima.
Trabalhamos com protocolos baseados em evidências e produtos de alta qualidade, com médicos certificados pelo CFM.',
'{"keywords": ["sobre", "clínica", "missão", "quem somos"]}'),

(:TENANT_ID, 'empresa', 'Diferenciais da clínica',
'Nossos diferenciais:
- Médicos especializados com mais de 5 anos de experiência em estética
- Avaliação gratuita antes de qualquer procedimento
- Técnica conservadora e natural — resultados discretos e elegantes
- Produtos importados de qualidade certificada (Allergan, Merz, Galderma)
- Ambiente seguro, discreto e acolhedor
- Pós-procedimento acompanhado com retorno gratuito em 14 dias',
'{"keywords": ["diferencial", "qualidade", "experiência", "segurança"]}');

-- ─── CONTATO ─────────────────────────────────────────────────

INSERT INTO wa_kb_entities (tenant_id, category, title, content, metadata) VALUES
(:TENANT_ID, 'contato', 'Endereço e localização',
'Estamos localizados no coração da cidade, de fácil acesso por transporte público e com estacionamento próximo.
Endereço: Rua das Flores, 123 — Sala 45 — Centro
CEP: 01310-100 | Cidade: São Paulo / SP
Como chegar: metrô linha 2 — estação República, saída B (2 minutos a pé).',
'{"keywords": ["endereço", "localização", "como chegar", "onde fica"]}'),

(:TENANT_ID, 'contato', 'Horário de funcionamento',
'Funcionamos de segunda a sábado:
- Segunda a sexta: 9h às 19h
- Sábado: 9h às 14h
- Domingo e feriados: fechado
Agendamentos pelo WhatsApp ou pelo link da bio do Instagram.',
'{"keywords": ["horário", "funcionamento", "quando", "abre", "fecha"]}'),

(:TENANT_ID, 'contato', 'Redes sociais e contato',
'Instagram: @clinica_exemplo (DM aberto para dúvidas rápidas)
WhatsApp: este mesmo número que você está usando agora
E-mail: contato@clinicaexemplo.com.br
Para agendamentos, prefira o WhatsApp — resposta mais rápida.',
'{"keywords": ["instagram", "redes sociais", "email", "contato", "WhatsApp"]}');

-- ─── SERVIÇOS ─────────────────────────────────────────────────

INSERT INTO wa_kb_entities (tenant_id, category, title, content, metadata) VALUES
(:TENANT_ID, 'servico', 'Botox (toxina botulínica)',
'O botox é uma das nossas especialidades. Utilizamos técnica ultra-conservadora para resultados naturais.
O que trata: linhas de expressão (testa, pés de galinha, entre sobrancelhas), bruxismo, hiperidrose, Nefertiti lift (pescoço e oval do rosto).
Duração dos resultados: 4 a 6 meses em média.
Procedimento: consulta de avaliação → aplicação (15-20 min) → retorno em 14 dias incluído.
Efeito completo: visível a partir do 5º ao 14º dia após aplicação.',
'{"keywords": ["botox", "toxina", "bótox", "expressão", "rugas", "testa", "bruxismo"]}'),

(:TENANT_ID, 'servico', 'Preenchimento com ácido hialurônico',
'Ácido hialurônico para volumização e hidratação profunda. Resultados naturais e reversíveis.
Indicações: lábios, maçãs do rosto, olheiras, bigode chinês, queixo, nariz não cirúrgico.
Duração: 6 a 18 meses dependendo da região e metabolismo.
Reversível: sim — com enzima hialuronidase caso necessite.
Marcas utilizadas: Juvederm (Allergan), Restylane (Galderma), Belotero (Merz).',
'{"keywords": ["preenchimento", "ácido hialurônico", "lábios", "bigode chinês", "olheiras", "volumização"]}'),

(:TENANT_ID, 'servico', 'Bioestimuladores de colágeno',
'Estimulam a produção natural de colágeno para rejuvenescimento progressivo e duradouro.
Produtos disponíveis: Sculptra (PLLA), Radiesse (CaHA), Ellansé (PCL).
Indicações: flacidez leve a moderada, perda de volume, qualidade de pele.
Duração: 18 meses a 2+ anos dependendo do produto.
Sessões: geralmente 2 a 3 sessões com intervalo de 30 dias.',
'{"keywords": ["bioestimulador", "colágeno", "sculptra", "radiesse", "flacidez", "rejuvenescimento"]}'),

(:TENANT_ID, 'servico', 'Limpeza de pele e skincare',
'Limpeza de pele profunda realizada por esteticista especializada sob supervisão médica.
Inclui: higienização, esfoliação, extração manual, máscara calmante, hidratação e fotoproteção.
Indicada para: todos os tipos de pele, acne leve a moderada, poros dilatados, opacidade.
Duração da sessão: 60 a 90 minutos. Recomendamos uma vez por mês para manutenção.',
'{"keywords": ["limpeza de pele", "skincare", "acne", "poros", "extração"]}'),

(:TENANT_ID, 'servico', 'Harmonização facial completa',
'Harmonização facial combina múltiplos procedimentos em um planejamento personalizado.
Pode incluir: botox + preenchimento + bioestimulador + skinbooster.
Objetivo: equilíbrio das proporções faciais respeitando a individualidade do paciente.
Avaliação essencial: toda harmonização começa com consulta detalhada de planejamento.
Resultado: progressivo, natural e personalizado — nunca padronizado.',
'{"keywords": ["harmonização", "harmonização facial", "procedimentos", "planejamento", "rosto"]}');

-- ─── PRECIFICAÇÃO ─────────────────────────────────────────────

INSERT INTO wa_kb_entities (tenant_id, category, title, content, metadata) VALUES
(:TENANT_ID, 'precificacao', 'Política de valores',
'Não divulgamos valores fechados pelo WhatsApp porque cada tratamento é personalizado.
O valor depende de: quantidade de produto utilizado, regiões tratadas, protocolo escolhido.
O que sempre fazemos: avaliação gratuita e sem compromisso onde apresentamos um orçamento detalhado.
Faixa orientativa (valores podem variar):
- Botox: a partir de R$ 800 por região
- Preenchimento: a partir de R$ 1.200 por seringa
- Bioestimulador: a partir de R$ 1.500 por sessão
Parcelamento disponível em até 12x no cartão de crédito.',
'{"keywords": ["preço", "valor", "quanto custa", "custo", "orçamento", "parcelado", "pagamento"]}'),

(:TENANT_ID, 'precificacao', 'Formas de pagamento',
'Aceitamos:
- Cartão de crédito: até 12x sem juros (Visa, Mastercard, Amex)
- Cartão de débito
- Pix (desconto de 5% à vista)
- Dinheiro
Não aceitamos: cheque ou boleto.
Nota fiscal emitida para todos os procedimentos.',
'{"keywords": ["pagamento", "parcelamento", "pix", "cartão", "débito", "crédito", "nota fiscal"]}');

-- ─── FAQ ─────────────────────────────────────────────────────

INSERT INTO wa_kb_entities (tenant_id, category, title, content, metadata) VALUES
(:TENANT_ID, 'faq', 'Grávida pode fazer botox ou preenchimento?',
'Não. Durante a gravidez, todos os procedimentos estéticos injetáveis são contraindicados por segurança.
Não há estudos suficientes sobre o impacto nos fetos. Aguardamos o fim da gestação e da amamentação.
Podemos fazer: consulta de planejamento para depois do período.',
'{"keywords": ["grávida", "gravidez", "gestante", "pode fazer"]}'),

(:TENANT_ID, 'faq', 'Amamentando pode fazer procedimentos?',
'Por precaução, orientamos aguardar o fim da amamentação para procedimentos injetáveis.
Alguns médicos liberam após 3 meses de amamentação estabelecida, mas nossa política é aguardar para garantir total segurança.
Tratamentos de pele não injetáveis (limpeza, hidratação) podem ser avaliados caso a caso.',
'{"keywords": ["amamentando", "amamentação", "lactante", "bebê"]}'),

(:TENANT_ID, 'faq', 'O botox vai me deixar com cara de "plástica" ou artificial?',
'Na nossa abordagem, isso não acontece. Nossa técnica é conservadora e personalizada.
Usamos doses menores e pontos estratégicos para manter expressão natural.
Na avaliação mostramos fotos de resultados reais dos nossos pacientes. O objetivo é que ninguém perceba que você fez — só que você está mais descansada e bonita.',
'{"keywords": ["artificial", "plástica", "exagerado", "natural", "expressão", "percebe"]}'),

(:TENANT_ID, 'faq', 'Dói? É preciso anestesia?',
'A maioria dos procedimentos tem desconforto mínimo. Usamos creme anestésico tópico 30 minutos antes.
Botox: sensação de picadinha leve, tolerada facilmente pela maioria.
Preenchimento com cânula: menos incômodo que seringa — usamos esta técnica sempre que possível.
Para quem tem baixa tolerância à dor, temos opções de anestesia local adicional.',
'{"keywords": ["dói", "dor", "anestesia", "incômodo", "picada"]}'),

(:TENANT_ID, 'faq', 'Quanto tempo duram os resultados?',
'Depende do procedimento:
- Botox: 4 a 6 meses (músculo gradualmente retoma atividade)
- Preenchimento: 6 a 18 meses (varia por região e metabolismo)
- Bioestimulador: 18 meses a 2+ anos
- Limpeza de pele: benefícios acumulam com sessões mensais
Manutenção regular garante resultados mais duradouros e naturais ao longo do tempo.',
'{"keywords": ["duração", "quanto tempo", "dura", "manutenção", "retoque"]}'),

(:TENANT_ID, 'faq', 'Posso combinar botox e preenchimento na mesma sessão?',
'Sim! Essa é uma combinação muito comum e eficaz. Na mesma sessão podemos fazer botox nas linhas de expressão e preenchimento nos lábios, por exemplo.
A avaliação define a melhor sequência para cada caso.
Combinações são planejadas para potencializar resultados com menos sessões.',
'{"keywords": ["combinar", "juntar", "mesma sessão", "dois procedimentos"]}'),

(:TENANT_ID, 'faq', 'Tem algum efeito colateral ou risco?',
'Todo procedimento médico tem riscos, mas são raros com profissionais qualificados.
Comuns e temporários: inchaço, roxinho, vermelhidão local por 24-72h.
Raros com técnica correta: assimetria (corrigível), hematoma.
Muito raros: reações alérgicas (por isso avaliamos histórico antes).
Nossa taxa de complicações é mínima. Acompanhamos todos os pacientes no pós-procedimento.',
'{"keywords": ["risco", "efeito colateral", "complicação", "seguro", "roxo", "inchaço"]}'),

(:TENANT_ID, 'faq', 'Preciso de receita ou encaminhamento médico?',
'Não. Você agenda diretamente pela nossa recepção ou WhatsApp.
A avaliação com nosso médico acontece na própria clínica. Ele avalia, indica o procedimento adequado e realiza — tudo no mesmo local.',
'{"keywords": ["receita", "encaminhamento", "médico", "preciso de"]}'),

(:TENANT_ID, 'faq', 'Posso maquiar depois? Quando posso lavar o rosto?',
'Botox: evitar maquiagem e atividade física por 4h. Pode lavar o rosto suavemente após 2h.
Preenchimento: evitar maquiagem por 24h e massagens na área por 2 semanas.
Limpeza de pele: pode lavar o rosto suavemente após o procedimento. Evitar sol e maquiagem por 24-48h.',
'{"keywords": ["maquiagem", "lavar rosto", "pós-procedimento", "cuidados", "pode fazer depois"]}'),

(:TENANT_ID, 'faq', 'Qual a idade mínima para fazer procedimentos estéticos?',
'Maior de 18 anos: autonomia total para decidir.
Entre 16 e 17 anos: necessário autorização dos pais ou responsável legal, por escrito.
Menores de 16 anos: não realizamos procedimentos estéticos eletivos.
Exceção: casos dermatológicos com indicação médica, avaliados individualmente.',
'{"keywords": ["idade", "menor", "adolescente", "18 anos", "autorização"]}');

-- ─── POLÍTICA ─────────────────────────────────────────────────

INSERT INTO wa_kb_entities (tenant_id, category, title, content, metadata) VALUES
(:TENANT_ID, 'politica', 'Política de cancelamento',
'Cancelamentos e remarcações:
- Com mais de 24h de antecedência: sem custo, reagendamos sem problema.
- Com menos de 24h ou no-show: cobramos 50% do valor do procedimento agendado.
- Emergências são avaliadas caso a caso com compreensão.
Por favor, avise com antecedência — isso nos permite oferecer o horário a outro paciente.',
'{"keywords": ["cancelamento", "remarcar", "desmarcar", "horário", "aviso", "multa"]}'),

(:TENANT_ID, 'politica', 'Política de privacidade (LGPD)',
'Coletamos apenas dados necessários para seu atendimento (nome, contato, histórico de saúde relevante).
Seus dados não são compartilhados com terceiros sem consentimento.
Fotos antes/depois: tiradas para avaliação clínica. Publicamos apenas com autorização expressa.
Para solicitar exclusão de dados: email contato@clinicaexemplo.com.br.
Armazenamento seguro conforme LGPD (Lei 13.709/2018).',
'{"keywords": ["privacidade", "LGPD", "dados", "fotos", "autorização", "compartilhar"]}');
