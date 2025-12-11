-- Reset Discovery Topics to a clean slate
TRUNCATE TABLE discovery_topics CASCADE;

-- Re-seed with high-quality, broad core topics
INSERT INTO discovery_topics (topic) VALUES 
('Unexplained archaeological findings 2025'),
('Recent anomalies in physics experiments'),
('Bioluminescence discoveries deep sea'),
('Cognitive science counterintuitive findings'),
('Animal migration pattern anomalies'),
('Technological glitches in large scale systems'),
('Declassified government documents strange details'),
('Unexplained atmospheric phenomena scientific reports'),
('Evolutionary anomalies and dead ends'),
('Out of place artifacts in historical records'),
('Signal anomalies in radio astronomy'),
('Unexplained geological formations recently discovered');
