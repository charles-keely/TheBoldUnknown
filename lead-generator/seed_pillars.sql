
-- Clear existing pillars to ensure a clean slate aligned with new brand guidelines
TRUNCATE TABLE brand_pillars;

INSERT INTO brand_pillars (name, description) VALUES
  ('Declassified & Intelligence', 'Intelligence archives, redactions, MK-Ultra, verified government programs, surveillance tech'),
  ('Ancient History & Lost Knowledge', 'Archaeology, OOPARTS, historical oddities, civilization collapse, lost technologies'),
  ('Anomalies & High Strangeness', 'Remote viewing, psi research, strange coincidences, The Gateway Process, anomalous cognition'),
  ('Cosmic & Scientific Mysteries', 'Quantum physics, cosmology, NASA audio/video anomalies, non-human intelligence signatures'),
  ('Consciousness & Perception', 'Dreams, deja vu, memory glitches, intuition, altered states, near-death experiences'),
  ('Credible Witness Reports', 'Mass sightings, shared encounters, pilot testimony, multi-witness high strangeness events');
