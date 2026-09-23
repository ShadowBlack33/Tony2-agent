-- Esquema destino PostgreSQL (Etapa 1-2). Referencia: pestana "Modelo de Datos".
-- Estado: validado en PostgreSQL 16 + pgvector 0.6 (crea 13 tablas sin errores).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE horma (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE horma_talla (
  horma_id UUID REFERENCES horma(id) ON DELETE CASCADE,
  talla_label TEXT NOT NULL,
  largo_plantilla_cm NUMERIC(4,1) NOT NULL CHECK (largo_plantilla_cm BETWEEN 10 AND 35),
  PRIMARY KEY (horma_id, talla_label)
);

CREATE TABLE producto (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo_modelo TEXT UNIQUE NOT NULL,
  nombre TEXT NOT NULL,
  linea TEXT,
  categoria TEXT NOT NULL CHECK (categoria IN ('guayo','guante','balon','media','canillera')),
  segmento TEXT CHECK (segmento IN ('adulto','nino','unisex')),
  material_principal TEXT,
  origen TEXT CHECK (origen IN ('fabricado','importado')),
  horma_id UUID REFERENCES horma(id),
  descripcion TEXT,
  estado TEXT DEFAULT 'activo',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE variante (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  producto_id UUID REFERENCES producto(id) ON DELETE CASCADE,
  sku TEXT UNIQUE NOT NULL,
  color TEXT,
  talla_label TEXT,
  suela TEXT CHECK (suela IN ('FG','AG','TF','IC','NA')),
  precio_lista INTEGER CHECK (precio_lista > 0),
  costo_unitario INTEGER,
  activo BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE inventario (
  variante_id UUID REFERENCES variante(id) ON DELETE CASCADE,
  ubicacion TEXT DEFAULT 'principal',
  cantidad INTEGER NOT NULL DEFAULT 0,
  sincronizado_en TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (variante_id, ubicacion)
);

-- Dimension del vector segun el modelo de embeddings elegido (ajustar).
CREATE TABLE producto_embedding (
  producto_id UUID PRIMARY KEY REFERENCES producto(id) ON DELETE CASCADE,
  texto_fuente TEXT NOT NULL,
  embedding vector(1024),
  actualizado_en TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON producto_embedding USING hnsw (embedding vector_cosine_ops);
CREATE INDEX producto_fts ON producto USING gin (to_tsvector('spanish', coalesce(nombre,'') || ' ' || coalesce(descripcion,'')));

CREATE TABLE venta (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fecha DATE NOT NULL,
  canal TEXT CHECK (canal IN ('tienda','whatsapp','web','instagram','distribuidor','marketplace')),
  cliente_id UUID,
  distribuidor_id UUID,
  ciudad TEXT,
  total INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE venta_linea (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  venta_id UUID REFERENCES venta(id) ON DELETE CASCADE,
  variante_id UUID REFERENCES variante(id),
  cantidad INTEGER NOT NULL CHECK (cantidad > 0),
  precio_unitario INTEGER NOT NULL,
  descuento INTEGER DEFAULT 0
);

CREATE TABLE demanda_no_cubierta (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fecha TIMESTAMPTZ DEFAULT now(),
  canal TEXT,
  consulta TEXT,
  filtros JSONB,
  motivo TEXT,
  usuario_id UUID
);

-- Perfiles: PII cifrada en la aplicacion (envelope encryption con KMS); *_hash = HMAC para busqueda.
CREATE TABLE usuario (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  estado TEXT DEFAULT 'activo',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE cliente_perfil (
  usuario_id UUID PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
  nombre_enc BYTEA,
  telefono_enc BYTEA,
  telefono_hash BYTEA UNIQUE,
  email_enc BYTEA,
  email_hash BYTEA UNIQUE,
  cedula_enc BYTEA,
  ciudad TEXT,
  direccion_envio_enc BYTEA,
  declara_mayor_edad BOOLEAN NOT NULL DEFAULT false,
  fecha_declaracion TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE consentimiento (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES usuario(id) ON DELETE CASCADE,
  version_politica TEXT NOT NULL,
  finalidades JSONB NOT NULL,
  canal TEXT,
  otorgado_en TIMESTAMPTZ DEFAULT now(),
  revocado_en TIMESTAMPTZ
);

CREATE TABLE auditoria (
  id BIGSERIAL PRIMARY KEY,
  actor_id UUID,
  accion TEXT NOT NULL,
  recurso TEXT NOT NULL,
  recurso_id TEXT,
  ts TIMESTAMPTZ DEFAULT now(),
  metadata JSONB
);
REVOKE UPDATE, DELETE ON auditoria FROM PUBLIC;
