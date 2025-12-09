-- Seed the discovery_topics table with initial high-quality search vectors
-- These are derived directly from the 'TheBoldUnknown' brand guide to kickstart the fractal engine.

INSERT INTO discovery_topics (topic) VALUES 
('Time perception anomalies in extreme environments'),
('Bioluminescence in unexpected ecosystems'),
('Acoustic levitation research'),
('Mycelial network intelligence'),
('Non-evolutionary biological traits'),
('Scientific analysis of Out-of-Place Artifacts (OOPArts)'),
('Unexplained atmospheric electrical phenomena'),
('Cognitive decoupling studies'),
('Quantum effects in biological systems'),
('Historical mass psychogenic illness events'),
('Transient radio signals from unknown sources'),
('Geological formations defying standard erosion models'),
('Deep sea gigantism mechanisms'),
('Plant signaling and "neurobiology"'),
('Archeoastronomy alignment anomalies'),
('The "Hum" phenomenon scientific investigations'),
('Retrocausality in quantum physics'),
('Panpsychism in modern neuroscience'),
('Unsolved mathematical tiling problems'),
('Anomalous aerodynamic properties in nature')
ON CONFLICT (topic) DO NOTHING;
