'use strict';
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat, TableOfContents,
  VerticalAlign, TabStopType
} = require('docx');
const fs = require('fs');

const PW = 11906, PH = 16838, MAR = 1418, CW = PW - MAR * 2; // A4, 2.5cm margins

// ─── Helpers ─────────────────────────────────────────────────────────────────

const sp = (n = 1) => Array.from({ length: n }, () => new Paragraph({ children: [new TextRun('')] }));
const pb = () => new Paragraph({ children: [new PageBreak()] });

function run(text, o = {}) {
  return new TextRun({ text, font: 'Arial', size: 24, ...o });
}

function par(children, o = {}) {
  return new Paragraph({
    alignment: o.align ?? AlignmentType.JUSTIFIED,
    spacing: o.spacing ?? { after: 200, line: 360 },
    ...(o.border   ? { border: o.border }     : {}),
    ...(o.shading  ? { shading: o.shading }   : {}),
    ...(o.indent   ? { indent: o.indent }     : {}),
    ...(o.heading  ? { heading: o.heading }   : {}),
    ...(o.pbBefore ? { pageBreakBefore: true } : {}),
    children
  });
}

function body(text, o = {}) {
  return par([run(text, o)], { align: o.center ? AlignmentType.CENTER : AlignmentType.JUSTIFIED });
}

function bul(text) {
  return new Paragraph({
    numbering: { reference: 'bul', level: 0 },
    spacing: { after: 100, line: 360 },
    children: [run(text)]
  });
}

// Chapter separator page  ->  H1 (TOC level 1)
function chap(n, title) {
  return [
    pb(),
    ...sp(7),
    par([run('Chapitre ' + n, { bold: true, size: 72, color: '2E75B6' })], {
      heading: HeadingLevel.HEADING_1,
      align: AlignmentType.CENTER,
      spacing: { before: 0, after: 240 }
    }),
    par([run(title, { bold: true, size: 36, color: '1F3864' })], {
      align: AlignmentType.CENTER,
      spacing: { before: 240, after: 240 },
      border: {
        top: { style: BorderStyle.SINGLE, size: 8, color: '2E75B6', space: 8 },
        bottom: { style: BorderStyle.SINGLE, size: 8, color: '2E75B6', space: 8 }
      }
    }),
    pb()
  ];
}

// Section  ->  H2 (TOC level 2)
function sec(label, title) {
  return par([run(label + '  ' + title, { bold: true, size: 28, color: '1F3864' })], {
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 400, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 4 } }
  });
}

// Subsection  ->  H3 (TOC level 3)
function sub(label, title) {
  return par([run(label + '  ' + title, { bold: true, size: 26, color: '2E75B6' })], {
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 300, after: 140 }
  });
}

// Sub-subsection  ->  H4 (TOC level 4)
function ssub(label, title) {
  return par([run(label + '  ' + title, { bold: true, italics: true, size: 24, color: '1F3864' })], {
    heading: HeadingLevel.HEADING_4,
    spacing: { before: 220, after: 100 }
  });
}

// Photo placeholder
function photo(desc, h = 2400) {
  return [
    new Table({
      width: { size: CW, type: WidthType.DXA },
      columnWidths: [CW],
      rows: [new TableRow({
        height: { value: h, rule: 'atLeast' },
        children: [new TableCell({
          width: { size: CW, type: WidthType.DXA },
          shading: { fill: 'F2F2F2', type: ShadingType.CLEAR },
          borders: {
            top:    { style: BorderStyle.DASHED, size: 6, color: '999999' },
            bottom: { style: BorderStyle.DASHED, size: 6, color: '999999' },
            left:   { style: BorderStyle.DASHED, size: 6, color: '999999' },
            right:  { style: BorderStyle.DASHED, size: 6, color: '999999' }
          },
          margins: { top: 400, bottom: 400, left: 200, right: 200 },
          verticalAlign: VerticalAlign.CENTER,
          children: [par(
            [run("[ Capture d'écran : " + desc + " ]", { italics: true, color: '777777', size: 22 })],
            { align: AlignmentType.CENTER, spacing: {} }
          )]
        })]
      })]
    }),
    par([run('')], { spacing: { after: 60 } })
  ];
}

function figcap(n, t) {
  return par([run('Figure ' + n + ' : ' + t, { italics: true, color: '555555', size: 20 })],
    { align: AlignmentType.CENTER, spacing: { after: 300 } });
}
function tabcap(n, t) {
  return par([run('Tableau ' + n + ' : ' + t, { bold: true, color: '555555', size: 20 })],
    { align: AlignmentType.CENTER, spacing: { before: 80, after: 300 } });
}

const CB = { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' };
const BORD = { top: CB, bottom: CB, left: CB, right: CB };

function tbl(heads, rows, cols) {
  return new Table({
    width: { size: CW, type: WidthType.DXA },
    columnWidths: cols,
    rows: [
      new TableRow({
        tableHeader: true,
        children: heads.map((h, i) => new TableCell({
          width: { size: cols[i], type: WidthType.DXA },
          shading: { fill: '2E75B6', type: ShadingType.CLEAR },
          borders: BORD,
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          verticalAlign: VerticalAlign.CENTER,
          children: [par([run(h, { bold: true, color: 'FFFFFF', size: 22 })], { align: AlignmentType.CENTER, spacing: {} })]
        }))
      }),
      ...rows.map((row, ri) => new TableRow({
        children: row.map((cell, ci) => new TableCell({
          width: { size: cols[ci], type: WidthType.DXA },
          shading: { fill: ri % 2 === 0 ? 'FFFFFF' : 'EEF4FA', type: ShadingType.CLEAR },
          borders: BORD,
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [par([run(String(cell), { size: 22 })], { align: AlignmentType.LEFT, spacing: {} })]
        }))
      }))
    ]
  });
}

function miniTitle(text) {
  return par([run(text, { bold: true, size: 26, color: '1F3864' })],
    { spacing: { before: 240, after: 120 } });
}

function frontTitle(text) {
  return par([run(text, { bold: true, size: 36, color: '1F3864' })], {
    align: AlignmentType.CENTER,
    spacing: { before: 200, after: 400 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 4 } }
  });
}

// ─── Page de garde ───────────────────────────────────────────────────────────

function cover() {
  return [
    ...sp(5),
    par([run('RAPPORT DE PROJET', { bold: true, size: 22, color: '888888' })],
      { align: AlignmentType.CENTER, spacing: { after: 80 } }),
    par([run('Application de Quiz Pédagogiques Interactifs', { bold: true, size: 44, color: '1F3864' })],
      { align: AlignmentType.CENTER, spacing: { after: 100 } }),
    par([run('en Réseau Local', { bold: true, size: 44, color: '1F3864' })], {
      align: AlignmentType.CENTER,
      spacing: { after: 280 },
      border: { bottom: { style: BorderStyle.THICK, size: 10, color: '2E75B6', space: 8 } }
    }),
    par([run("Un système d'évaluation formative interactive pour la salle de classe",
      { italics: true, size: 24, color: '2E75B6' })],
      { align: AlignmentType.CENTER, spacing: { after: 800 } }),
    ...sp(2),
    par([run('Réalisé par :   ', { size: 22, color: '666666' }),
      run("[NOM DE L'ÉTUDIANT(E)]", { bold: true, size: 28, color: '1F3864' })],
      { align: AlignmentType.CENTER, spacing: { after: 160 } }),
    par([run('Encadré par :   ', { size: 22, color: '666666' }),
      run('[NOM DU PROFESSEUR]', { bold: true, size: 24, color: '1F3864' })],
      { align: AlignmentType.CENTER, spacing: { after: 160 } }),
    par([run('Établissement :   ', { size: 22, color: '666666' }),
      run("[NOM DE L'ÉTABLISSEMENT]", { bold: true, size: 24, color: '1F3864' })],
      { align: AlignmentType.CENTER, spacing: { after: 160 } }),
    par([run('Filière :   ', { size: 22, color: '666666' }),
      run('[FILIÈRE / SPÉCIALITÉ]', { bold: true, size: 24, color: '1F3864' })],
      { align: AlignmentType.CENTER, spacing: { after: 160 } }),
    par([run('Année scolaire :   ', { size: 22, color: '666666' }),
      run('2024 – 2025', { bold: true, size: 24, color: '1F3864' })],
      { align: AlignmentType.CENTER, spacing: { after: 160 } }),
  ];
}

// ─── Remerciement ────────────────────────────────────────────────────────────

function remerciement() {
  return [
    pb(),
    frontTitle('Remerciement'),
    body("Au terme de ce travail, je tiens à exprimer ma profonde gratitude à toutes les personnes qui ont contribué, de près ou de loin, à la réalisation de ce projet."),
    body("Je remercie en premier lieu mon professeur encadrant, [NOM DU PROFESSEUR], pour son accompagnement tout au long de ce projet, ses conseils précieux et sa disponibilité constante. Ses orientations m'ont permis d'avancer avec rigueur et méthode."),
    body("Je remercie également l'ensemble du corps enseignant de [NOM DE L'ÉTABLISSEMENT] pour la qualité de la formation dispensée durant cette année."),
    body("Mes remerciements vont aussi à ma famille pour son soutien moral constant et ses encouragements durant toutes les étapes de ce travail."),
    body("Enfin, je remercie tous mes camarades et amis pour leur aide, leurs conseils et les échanges enrichissants que nous avons eus tout au long de ce projet."),
  ];
}

// ─── Résumé ──────────────────────────────────────────────────────────────────

function resume() {
  return [
    pb(),
    frontTitle('Résumé'),
    body("Ce projet présente la conception et le développement d'une application de quiz pédagogiques interactifs fonctionnant en réseau local. L'objectif principal est d'améliorer le processus d'évaluation formative en classe en le rendant plus rapide, plus engageant et plus efficace."),
    body("L'application permet à l'enseignant de créer et gérer des quiz, de lancer des sessions en temps réel et de consulter des statistiques détaillées sur les performances des élèves. De leur côté, les élèves rejoignent les sessions depuis leurs appareils via un navigateur web, répondent aux questions dans un ordre aléatoire propre à chacun, et reçoivent un feedback immédiat après chaque réponse."),
    body("Le système repose sur une architecture client-serveur en réseau local, avec une communication en temps réel grâce aux WebSockets. La base de données SQLite assure la persistance des données. L'application est développée en Python avec le framework FastAPI, et les interfaces sont construites en HTML, CSS et JavaScript. L'ensemble du système fonctionne sans connexion Internet."),
    body("Les principales fonctionnalités sont : la création et la gestion de quiz, le lancement de sessions interactives, un système de points et de classement, un feedback immédiat après chaque réponse, et un système de statistiques pédagogiques à trois niveaux (par session, par quiz et par élève)."),
    par([run('Mots-clés : ', { bold: true, size: 22 }),
      run("évaluation formative, quiz interactif, réseau local, FastAPI, WebSocket, gamification, statistiques pédagogiques",
        { italics: true, size: 22, color: '444444' })],
      { spacing: { after: 300 } }),
    par([run('Abstract', { bold: true, size: 30, color: '1F3864' })], {
      spacing: { before: 300, after: 180 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: 'CCCCCC', space: 3 } }
    }),
    body('This project presents the design and development of an interactive pedagogical quiz application running on a local network. The main objective is to improve the formative assessment process in the classroom by making it faster, more engaging and more effective. The system uses a client-server architecture with FastAPI (Python) and WebSockets for real-time communication, and SQLite for local data storage. Key features include quiz creation, real-time sessions, a scoring and ranking system, immediate feedback, and a three-level statistical analysis system (by session, by quiz and by student). No Internet connection is required.'),
    par([run('Keywords: ', { bold: true, size: 22 }),
      run('formative assessment, interactive quiz, local network, FastAPI, WebSocket, gamification, educational statistics',
        { italics: true, size: 22, color: '444444' })],
      { spacing: { after: 200 } }),
  ];
}

// ─── Listes ───────────────────────────────────────────────────────────────────

function listeFigures() {
  return [
    pb(),
    frontTitle('Liste des figures'),
    tbl(
      ['N°', 'Titre de la figure', 'Page'],
      [
        ['Figure 1',  'Architecture client-serveur en réseau local', '—'],
        ['Figure 2',  'Schéma de la base de données (ERD)', '—'],
        ['Figure 3',  'Tableau de bord enseignant', '—'],
        ["Figure 4",  "Page de connexion et d'inscription des élèves", '—'],
        ['Figure 5',  'Interface de jeu – question en cours', '—'],
        ['Figure 6',  'Classement final (leaderboard)', '—'],
        ['Figure 7',  'Feedback immédiat après réponse', '—'],
        ['Figure 8',  'Interface de contrôle de session (enseignant)', '—'],
        ["Figure 9",  "Éditeur de quiz – création d'une question", '—'],
        ['Figure 10', 'Statistiques par session', '—'],
        ['Figure 11', 'Statistiques par quiz', '—'],
        ['Figure 12', 'Statistiques par élève', '—'],
      ],
      [1500, 6570, 1000]
    ),
    par([run("Note : les numéros de page seront mis à jour après finalisation du document.",
      { italics: true, size: 20, color: '888888' })],
      { align: AlignmentType.CENTER, spacing: { before: 160, after: 0 } }),
  ];
}

function listeTableaux() {
  return [
    pb(),
    frontTitle('Liste des tableaux'),
    tbl(
      ['N°', 'Titre du tableau', 'Page'],
      [
        ['Tableau 1', 'Comparaison des outils de quiz existants', '—'],
        ["Tableau 2", "Stack technique de l'application", '—'],
        ['Tableau 3', 'Structure de la base de données', '—'],
        ['Tableau 4', 'Canaux WebSocket et leurs rôles', '—'],
        ["Tableau 5", "États d'une session de quiz", '—'],
      ],
      [1500, 6570, 1000]
    ),
    par([run("Note : les numéros de page seront mis à jour après finalisation du document.",
      { italics: true, size: 20, color: '888888' })],
      { align: AlignmentType.CENTER, spacing: { before: 160, after: 0 } }),
  ];
}

// ─── Chapitre 1 : Introduction Générale ──────────────────────────────────────

function chapter1() {
  return [
    ...chap(1, 'Introduction Générale'),

    sec('1', 'Introduction Générale'),
    body("Les outils numériques occupent aujourd'hui une place croissante dans les pratiques pédagogiques. Ils transforment la façon dont les enseignants évaluent leurs élèves et dont ces derniers reçoivent un retour sur leur travail. Dans ce contexte, repenser les méthodes classiques d'évaluation est devenu une nécessité pour améliorer l'efficacité pédagogique."),
    body("C'est dans cette perspective que s'inscrit ce projet : la conception et le développement d'une application de quiz pédagogiques interactifs fonctionnant en réseau local, destinée à moderniser le processus d'évaluation formative en classe."),

    sub('1.1', 'Contexte'),
    body("Dans une salle de classe classique, l'enseignant évalue régulièrement le niveau de compréhension de ses élèves, notamment à la fin d'un cours ou d'un module. Ces évaluations jouent un rôle important dans la consolidation des apprentissages et dans l'identification des lacunes."),
    body("Cependant, les outils traditionnels présentent plusieurs limites importantes. La correction manuelle des copies prend du temps et retarde le retour d'information aux élèves. Ce délai réduit l'impact pédagogique du feedback, qui est pourtant essentiel dans le processus d'apprentissage. De plus, le suivi individuel de chaque élève sur plusieurs séances reste difficile sans un système centralisé."),
    body("Par ailleurs, le manque d'interactivité dans les méthodes classiques peut réduire la motivation des élèves, qui perçoivent parfois ces activités comme répétitives ou peu stimulantes. L'intégration d'outils numériques dans l'évaluation devient donc nécessaire pour améliorer à la fois l'efficacité pédagogique et l'engagement des élèves."),

    sub('1.2', 'Problématique'),
    body("Dans un contexte où l'enseignement évolue vers des approches plus interactives et centrées sur l'apprenant, il devient essentiel de repenser les méthodes d'évaluation formative. Les outils existants, bien qu'efficaces, nécessitent généralement une connexion Internet stable, ce qui limite leur utilisation dans de nombreux établissements."),
    par([run("Comment concevoir une application d'évaluation formative interactive, fonctionnant sans connexion Internet, qui rende le processus d'évaluation plus rapide, plus motivant et plus efficace, tout en facilitant le suivi pédagogique et l'analyse des performances des apprenants ?",
      { bold: true, italics: true, size: 24, color: '1F3864' })], {
      align: AlignmentType.CENTER,
      spacing: { before: 200, after: 200 },
      border: {
        top:    { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 6 },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 6 }
      },
      indent: { left: 400, right: 400 }
    }),

    sub('1.3', 'Objectifs du projet'),
    body("L'objectif principal de ce projet est de concevoir et développer une application de quiz interactifs qui améliore l'évaluation formative en classe. De manière détaillée, ce projet vise à :"),
    bul("Proposer une solution numérique rendant l'évaluation formative plus interactive et plus engageante pour les apprenants."),
    bul("Offrir un retour immédiat après chaque réponse, afin d'améliorer la compréhension des erreurs et de favoriser l'apprentissage."),
    bul("Motiver les élèves grâce à un système de points et de classement inspiré de la gamification."),
    bul("Automatiser la correction des réponses et la gestion des résultats pour alléger la charge de l'enseignant."),
    bul("Centraliser les données pédagogiques pour permettre un meilleur suivi individuel des apprenants."),
    bul("Fournir un système de statistiques pédagogiques organisé selon trois niveaux : par session, par quiz et par élève."),
  ];
}

// ─── Chapitre 2 : Cadre théorique ────────────────────────────────────────────

function chapter2() {
  return [
    ...chap(2, "Cadre théorique et état de l'art"),

    sec('2', 'Cadres théoriques'),
    body("Ce chapitre présente les notions théoriques sur lesquelles repose le projet, ainsi qu'une analyse des outils existants dans le domaine des quiz éducatifs interactifs. Il vise à situer notre contribution par rapport aux solutions déjà en place."),

    sub('2.1', 'Évaluation formative'),
    body("L'évaluation formative est un processus pédagogique qui consiste à évaluer les apprenants tout au long de leur apprentissage, et non uniquement à la fin d'un module ou d'un cours. Son objectif principal est de suivre la progression des élèves, d'identifier leurs difficultés et d'adapter les méthodes d'enseignement en conséquence."),
    body("Contrairement à l'évaluation sommative, qui sert à attribuer une note finale, l'évaluation formative met l'accent sur l'amélioration continue. Dans ce cadre, le feedback joue un rôle essentiel : il permet à l'élève de comprendre ses erreurs, de corriger ses conceptions erronées et de progresser de manière consciente."),
    body("Cette forme d'évaluation est particulièrement efficace lorsqu'elle est accompagnée d'un retour rapide et explicatif. Plus le feedback est immédiat, plus il a d'impact sur les apprentissages. C'est l'un des principes fondateurs sur lesquels repose l'application développée dans ce projet."),

    sub('2.2', "Gamification dans l'éducation"),
    body("La gamification désigne l'application d'éléments et de mécaniques issus du jeu dans des contextes non ludiques, comme l'éducation. Elle inclut des mécanismes tels que les points, les niveaux, les badges et les classements."),
    body("Dans le domaine éducatif, la gamification est utilisée pour augmenter la motivation et l'engagement des apprenants. Elle transforme des activités parfois perçues comme répétitives en expériences interactives et stimulantes. Des études montrent que l'introduction de mécaniques ludiques dans les activités pédagogiques contribue à améliorer la concentration et la participation des élèves."),
    body("Dans le cadre de l'évaluation formative, la gamification permet de rendre les quiz plus attractifs. Un système de points attribués selon la rapidité et la justesse des réponses, associé à un classement en temps réel, incite les élèves à participer activement."),

    sub('2.3', 'Feedback pédagogique'),
    body("Le feedback pédagogique est l'information transmise à l'apprenant concernant la qualité de sa réponse ou de son travail. Dans les systèmes interactifs modernes, le feedback immédiat est fortement privilégié car il est plus efficace sur le plan pédagogique."),
    body("Un feedback efficace doit être clair, rapide et explicatif. Il ne se limite pas à indiquer si une réponse est correcte ou incorrecte, mais aide également l'élève à comprendre la logique derrière la bonne réponse. Dans l'application développée, le feedback est affiché immédiatement après chaque réponse, accompagné d'une explication pédagogique."),

    sub('2.4', 'Systèmes de quiz interactifs'),
    body("Les systèmes de quiz interactifs sont des plateformes numériques permettant de poser des questions aux apprenants et de recevoir leurs réponses en temps réel. Ils sont utilisés aussi bien en classe qu'en formation à distance, et permettent généralement :"),
    bul("La création de questionnaires dynamiques."),
    bul("La correction automatique des réponses."),
    bul("L'affichage immédiat des résultats."),
    bul("La génération de statistiques sur les performances."),
    body("Ces outils sont de plus en plus adoptés dans l'éducation moderne pour améliorer l'interaction entre enseignants et élèves."),

    sub('2.5', 'Étude des solutions existantes'),
    body("Plusieurs plateformes de quiz éducatifs sont largement utilisées dans les établissements scolaires. Parmi les plus connues, on peut citer Kahoot, Quizizz et Moodle Quiz."),

    ssub('2.5.1', 'Kahoot'),
    body("Kahoot est une plateforme en ligne très populaire permettant de créer des quiz interactifs. Les élèves répondent aux questions en temps réel via leurs appareils, et un classement est affiché après chaque question. Kahoot est apprécié pour sa simplicité d'utilisation et son aspect ludique."),
    body("Cependant, Kahoot nécessite une connexion Internet stable pour fonctionner, et les données des élèves sont hébergées sur des serveurs externes, ce qui peut poser des questions de confidentialité dans certains contextes scolaires."),

    ssub('2.5.2', 'Quizizz'),
    body("Quizizz est une plateforme éducative basée sur des quiz interactifs. Elle offre plus de flexibilité que Kahoot, notamment en permettant aux élèves de répondre à leur propre rythme. Elle propose également des rapports détaillés sur les performances individuelles."),
    body("Comme Kahoot, Quizizz est entièrement dépendant d'une connexion Internet et fonctionne via des serveurs en ligne."),

    ssub('2.5.3', 'Moodle Quiz'),
    body("Moodle est une plateforme d'apprentissage en ligne (LMS) très répandue dans les établissements scolaires et universitaires. Son module Quiz permet de créer des évaluations avec des fonctionnalités avancées comme la gestion des tentatives et la randomisation des questions."),
    body("Moodle offre de nombreuses possibilités, mais sa configuration est complexe et son interface est souvent moins adaptée à une utilisation rapide en classe."),

    sub('2.6', 'Analyse comparative'),
    body("L'analyse des solutions existantes permet de mettre en évidence leurs points forts et leurs limites par rapport aux besoins du contexte scolaire local."),
    tbl(
      ['Critère', 'Kahoot', 'Quizizz', 'Moodle', 'Notre application'],
      [
        ["Connexion Internet requise",   'Oui',     'Oui',     'Oui',    'Non'],
        ["Fonctionnement local",         'Non',     'Non',     'Non',    'Oui'],
        ["Feedback immédiat",            'Oui',     'Oui',     'Partiel','Oui'],
        ["Statistiques détaillées",      'Partiel', 'Oui',     'Oui',   'Oui'],
        ["Simplicité d'utilisation",     'Élevée',  'Élevée',  'Faible','Élevée'],
        ["Contrôle total de la session", 'Partiel', 'Partiel', 'Oui',   'Oui'],
        ["Suivi individuel par élève",   'Partiel', 'Oui',     'Oui',   'Oui'],
        ["Export des résultats",         'Partiel', 'Oui',     'Oui',   'Oui (Excel/CSV)'],
      ],
      [2800, 1500, 1500, 1500, 1770]
    ),
    tabcap(1, 'Comparaison des outils de quiz existants'),

    sub('2.7', 'Limites des solutions existantes'),
    body("Malgré leurs avantages, les plateformes existantes présentent des limites importantes dans le contexte scolaire local :"),
    bul("Dépendance à une connexion Internet stable, rendant ces outils inutilisables dans les établissements où la connectivité est insuffisante."),
    bul("Hébergement des données élèves sur des serveurs extérieurs, posant des questions de confidentialité."),
    bul("Contrôle limité de la session par l'enseignant dans certains outils."),
    bul("Suivi longitudinal des élèves parfois insuffisant sur plusieurs séances."),
    bul("Configuration complexe pour certains outils (notamment Moodle)."),

    sub('2.8', 'Valeur ajoutée de la solution proposée'),
    body("La solution développée dans ce projet répond directement aux limites identifiées. Elle fonctionne entièrement en réseau local, sans dépendance à une connexion Internet, et toutes les données sont stockées localement sur la machine de l'enseignant."),
    body("Elle donne à l'enseignant un contrôle total sur les sessions et intègre un système de statistiques pédagogiques complet, organisé selon trois niveaux d'analyse (par session, par quiz et par élève), permettant un suivi détaillé des performances des apprenants sur le long terme."),
  ];
}

// ─── Chapitre 3 : Cadre pratique ─────────────────────────────────────────────

function chapter3() {
  return [
    ...chap(3, 'Cadre pratique (Conception et réalisation)'),

    sec('3', 'Phase de conception'),
    body("La phase de conception est une étape fondamentale dans le développement de l'application. Elle permet de définir l'architecture générale du système, ses fonctionnalités principales et la manière dont les différents utilisateurs interagissent avec la plateforme."),

    // 3.1
    sub('3.1', 'Présentation générale du système'),
    body("Le système développé est une application éducative de quiz interactifs utilisée en salle de classe. Il met en relation deux types d'utilisateurs principaux :"),
    bul("L'enseignant : il est responsable de la création des quiz, du lancement des sessions, du contrôle du déroulement et de la consultation des résultats et statistiques."),
    bul("L'élève : il participe aux sessions de quiz via son appareil, répond aux questions et reçoit un feedback immédiat."),
    body("Un troisième élément peut être connecté : un écran de projection qui affiche en temps réel l'état de la session pour l'ensemble de la classe (code d'accès, QR code, classement). Cet écran est synchronisé automatiquement avec le serveur."),
    body("L'application transforme une évaluation classique en une activité dynamique basée sur des questions à choix multiples, avec un système de points, un temps limité par question et un feedback immédiat après chaque réponse."),

    // 3.2
    sub('3.2', 'Architecture du système'),
    body("L'architecture du système repose sur un modèle client-serveur en réseau local. L'ordinateur de l'enseignant joue le rôle de serveur central. Les appareils des élèves se connectent à ce serveur via leurs navigateurs web, sans nécessité d'installation."),
    ...photo("Schéma de l'architecture client-serveur en réseau local", 2800),
    figcap(1, 'Architecture client-serveur en réseau local'),

    miniTitle('Stack technique'),
    body("Le tableau suivant présente les technologies utilisées dans le développement de l'application."),
    tbl(
      ['Composant', 'Technologie', 'Rôle'],
      [
        ['Langage backend',         'Python 3.10+',    'Langage principal du serveur'],
        ['Framework web',           'FastAPI',         'Gestion des routes HTTP et WebSockets'],
        ['Serveur ASGI',            'Uvicorn',         'Exécution du serveur en mode asynchrone'],
        ['Base de données',         'SQLite',          'Stockage local des données'],
        ['Moteur de templates',     'Jinja2',          'Rendu des pages HTML côté serveur'],
        ['Communication temps réel','WebSockets',      'Synchronisation en temps réel'],
        ['Interface client',        'HTML, CSS, JS',   'Interfaces navigateur (sans installation)'],
        ['Exports',                 'xlsxwriter / csv','Export des résultats en Excel et CSV'],
      ],
      [2500, 2300, 4270]
    ),
    tabcap(2, "Stack technique de l'application"),

    miniTitle('Structure de la base de données'),
    tbl(
      ['Table', 'Contenu principal'],
      [
        ['quizzes',               'Titre, description et catégorie de chaque quiz'],
        ['questions',             'Texte, ordre, temps limite et index de la bonne réponse'],
        ['choices',               'Les options de réponse pour chaque question'],
        ['sessions',              'État, code de session, index de question courante'],
        ['students',              'Comptes élèves : pseudo, mot de passe haché, avatar'],
        ['players',               "Participants actifs d'une session"],
        ['answers',               'Réponses soumises par joueur et par question'],
        ['final_scores',          'Classement final de chaque session'],
        ['player_question_orders','Ordre aléatoire des questions par joueur'],
      ],
      [2500, 6570]
    ),
    tabcap(3, 'Structure de la base de données'),
    ...photo('Schéma de la base de données (diagramme entité-relation)', 3000),
    figcap(2, 'Schéma de la base de données (ERD)'),

    miniTitle('Communication en temps réel'),
    tbl(
      ['Canal WebSocket', 'Utilisateur', 'Rôle'],
      [
        ['/ws/teacher',         'Enseignant',          'Reçoit les événements et envoie les commandes de contrôle'],
        ['/ws/student/{token}', 'Élève',               'Reçoit les questions et soumet les réponses'],
        ['/ws/display',         'Écran de projection', 'Reçoit les mises à jour en lecture seule'],
      ],
      [2700, 1800, 4570]
    ),
    tabcap(4, 'Canaux WebSocket et leurs rôles'),

    // 3.3
    sub('3.3', "Fonctionnement général de l'application"),
    body("Le déroulement d'une session de quiz suit un cycle d'états bien défini, qui garantit une organisation claire de l'activité pédagogique."),
    tbl(
      ['État', 'Description'],
      [
        ['WAITING',         "La session est créée, les élèves peuvent rejoindre"],
        ['LOBBY',           "Salle d'attente : le quiz est sélectionné, on attend les participants"],
        ['QUESTION_ACTIVE', "Une question est affichée, les élèves peuvent répondre"],
        ['QUESTION_CLOSED', "La question est fermée, les réponses ne sont plus acceptées"],
        ['LEADERBOARD',     "Le classement intermédiaire est affiché"],
        ['FINISHED',        "La session est terminée, le classement final est affiché"],
      ],
      [2700, 6370]
    ),
    tabcap(5, "États d'une session de quiz"),
    body("Quand l'enseignant lance une question, le serveur notifie instantanément tous les élèves connectés via WebSocket. Chaque élève reçoit les questions dans un ordre aléatoire qui lui est propre, ce qui limite les effets de copie entre camarades. Après soumission d'une réponse, le serveur la valide, calcule le score et met à jour le classement en temps réel."),
    body("Le score est calculé selon un système inspiré de Kahoot : chaque bonne réponse rapporte 500 points de base, auxquels s'ajoute un bonus de rapidité pouvant atteindre 500 points supplémentaires, proportionnel au temps restant au moment de la soumission. Une mauvaise réponse ne rapporte aucun point."),
    ...photo("Tableau de bord enseignant – vue générale et contrôle de session", 2600),
    figcap(3, 'Tableau de bord enseignant'),

    // 3.4
    sub('3.4', "Description de l'application et apports pédagogiques"),
    body("Cette section décrit en détail les différentes fonctionnalités de l'application, en mettant en évidence leur apport pédagogique pour l'enseignant et les élèves."),

    ssub('3.4.1', 'Description générale'),
    body("L'application est une plateforme interactive de quiz pédagogiques destinée à soutenir l'évaluation formative en classe. Elle permet de transformer l'évaluation en une activité dynamique, motivante et interactive, tout en conservant un objectif pédagogique essentiel : l'amélioration des apprentissages."),
    body("L'application est utilisée principalement à la fin d'un module ou d'une séance afin d'évaluer rapidement le niveau de compréhension des élèves. Elle ne nécessite aucune installation côté élève : un simple navigateur web suffit."),

    ssub('3.4.2', 'Fonctionnement en réseau local'),
    body("L'application fonctionne entièrement en réseau local, où le poste de l'enseignant agit comme serveur et les élèves se connectent depuis leurs propres appareils (ordinateurs, tablettes ou smartphones)."),
    body("Ce mode de fonctionnement ne nécessite pas de connexion Internet, ce qui rend l'outil adapté aux environnements scolaires classiques où la connectivité peut être limitée. Toutes les données sont stockées localement sur la machine de l'enseignant, garantissant la confidentialité des résultats des élèves."),

    ssub('3.4.3', 'Accès simple et utilisation intuitive'),
    body("L'accès à l'application est simplifié grâce à un QR code affiché sur l'écran de projection au moment du lancement de la session. Les élèves n'ont qu'à le scanner avec leurs smartphones pour accéder directement à la page de connexion. Ils peuvent également saisir manuellement l'adresse IP du serveur dans leur navigateur."),
    body("Cette simplicité d'accès permet une utilisation rapide même pour des élèves ayant peu de compétences informatiques. Aucun téléchargement, aucune installation, aucun compte préalable n'est nécessaire pour rejoindre une session."),

    ssub('3.4.4', 'Comptes utilisateurs'),
    body("Chaque élève possède un compte personnel avec un pseudo unique, un mot de passe sécurisé et un avatar personnalisé. L'avatar est composé d'un personnage (parmi plus de 30 animaux), d'une couleur et d'un accessoire."),
    body("Ces comptes permettent une identification claire des participants et un suivi individualisé des performances sur plusieurs sessions. Le mot de passe est stocké de manière sécurisée via un hachage PBKDF2-SHA256. Deux modes de connexion sont disponibles : l'inscription (création d'un nouveau compte) ou la connexion (accès à un compte existant)."),
    ...photo("Page de connexion et d'inscription des élèves avec sélection d'avatar", 2600),
    figcap(4, "Page de connexion et d'inscription des élèves"),

    ssub('3.4.5', 'Déroulement des quiz'),
    body("Chaque session de quiz est lancée par l'enseignant depuis son tableau de bord. Les élèves répondent à des questions à choix multiples, chacun dans un ordre différent et aléatoire. Ce système de questions individuelles réduit les effets de copie et encourage le travail personnel."),
    body("Pour chaque question, un compte à rebours indique le temps restant. Une fois le temps écoulé ou après soumission de la réponse, l'élève passe automatiquement à la question suivante."),
    ...photo("Interface de jeu – question en cours avec compte à rebours", 2600),
    figcap(5, 'Interface de jeu – question en cours'),

    ssub('3.4.6', 'Système de points et motivation'),
    body("Les élèves gagnent des points en fonction de la rapidité et de la justesse de leurs réponses. Chaque bonne réponse rapporte 500 points de base, auxquels s'ajoute un bonus de rapidité proportionnel au temps restant (jusqu'à 500 points supplémentaires). Une mauvaise réponse ne rapporte aucun point."),
    body("Un classement est affiché après chaque question, puis en fin de session. Ce mécanisme introduit une dimension ludique et compétitive qui augmente significativement la motivation et l'engagement des élèves."),
    ...photo("Classement final – leaderboard affiché en fin de session", 2200),
    figcap(6, 'Classement final (leaderboard)'),

    ssub('3.4.7', 'Feedback immédiat'),
    body("Après chaque réponse, un feedback est affiché immédiatement à l'élève. Ce feedback indique si la réponse est correcte ou incorrecte et affiche une explication pédagogique rédigée par l'enseignant au moment de la création du quiz."),
    body("Ce mécanisme permet un apprentissage immédiat à partir des erreurs. L'élève comprend pourquoi sa réponse était incorrecte et retient la bonne information au moment même où elle est pertinente, maximisant ainsi l'impact pédagogique."),
    ...photo("Feedback immédiat après réponse – bonne réponse et explication", 2200),
    figcap(7, 'Feedback immédiat après réponse'),

    ssub('3.4.8', 'Suivi en temps réel'),
    body("L'enseignant peut suivre en temps réel la progression des élèves pendant la session depuis son interface de contrôle. Il peut voir l'avancement de chaque participant, le nombre de réponses soumises et l'état général de la session."),
    body("Cette visibilité en temps réel permet à l'enseignant d'adapter le rythme de la session : il peut décider de fermer une question plus tôt si tous les élèves ont répondu, ou attendre un peu plus si certains sont encore en train de réfléchir."),
    ...photo("Interface de contrôle de session – suivi en temps réel par l'enseignant", 2600),
    figcap(8, 'Interface de contrôle de session (enseignant)'),

    ssub('3.4.9', 'Gestion des quiz'),
    body("L'enseignant peut créer, modifier et supprimer des quiz depuis l'interface dédiée. Chaque quiz est composé d'un titre, d'une description, d'une catégorie et d'une liste de questions à choix multiples."),
    body("Pour chaque question, l'enseignant définit : le texte de la question, les quatre options de réponse, l'index de la bonne réponse, le temps limite (20 secondes par défaut) et une explication pédagogique. Les quiz peuvent être créés directement dans l'interface ou importés depuis un fichier JSON."),
    ...photo("Éditeur de quiz – création ou modification d'une question", 2800),
    figcap(9, "Éditeur de quiz – création d'une question"),

    ssub('3.4.10', 'Système de statistiques pédagogiques'),
    body("L'application intègre un système complet de statistiques permettant une analyse approfondie des performances des élèves. Ces statistiques constituent un élément central de l'application, car elles permettent à l'enseignant d'exploiter les données générées pendant les quiz afin de mieux comprendre les acquis et les difficultés des apprenants."),
    body("Les statistiques sont organisées selon trois niveaux complémentaires :"),
    par([run('Statistiques par session', { bold: true, size: 24, color: '2E75B6' })],
      { spacing: { before: 160, after: 80 } }),
    body("L'enseignant peut analyser le déroulement complet d'une séance de quiz. Il a accès à un résumé global, aux résultats par question (taux de réussite, distribution des réponses, temps moyen) et aux performances individuelles de chaque élève."),
    body("Apport pédagogique : permet d'identifier rapidement les notions mal comprises et d'ajuster l'enseignement pour les séances suivantes."),
    ...photo("Statistiques par session – résultats globaux et par question", 2600),
    figcap(10, 'Statistiques par session'),
    par([run('Statistiques par quiz', { bold: true, size: 24, color: '2E75B6' })],
      { spacing: { before: 160, after: 80 } }),
    body("L'enseignant peut analyser un même quiz sur plusieurs sessions différentes. Il peut observer les questions les plus difficiles, le taux de réussite de chaque question et la performance globale du quiz dans le temps."),
    body("Apport pédagogique : permet d'améliorer la qualité des évaluations en identifiant les questions mal comprises ou mal formulées."),
    ...photo("Statistiques par quiz – taux de réussite par question", 2600),
    figcap(11, 'Statistiques par quiz'),
    par([run('Statistiques par élève', { bold: true, size: 24, color: '2E75B6' })],
      { spacing: { before: 160, after: 80 } }),
    body("L'application permet un suivi individuel de chaque apprenant sur l'ensemble des sessions. L'enseignant peut voir l'évolution des scores, la progression dans le temps et les difficultés récurrentes de chaque élève."),
    body("Apport pédagogique : permet un accompagnement personnalisé et l'identification des élèves nécessitant un soutien particulier."),
    ...photo("Statistiques par élève – historique et évolution des scores", 2600),
    figcap(12, 'Statistiques par élève'),
    body("Les résultats peuvent être exportés au format Excel (.xlsx) ou CSV pour une exploitation hors application."),

    ssub('3.4.11', 'Enregistrement des sessions'),
    body("Toutes les sessions sont enregistrées dans la base de données avec les réponses des élèves, les scores et les temps de réponse obtenus. Cet enregistrement permet de conserver un historique complet des activités pédagogiques."),
    body("Apport pédagogique : garantit une traçabilité complète et permet une exploitation des données pour améliorer les pratiques pédagogiques futures. L'enseignant peut consulter les résultats de n'importe quelle session passée, même plusieurs semaines après."),
  ];
}

// ─── Chapitre 4 : Conclusion et perspectives ─────────────────────────────────

function chapter4() {
  return [
    ...chap(4, 'Conclusion et perspectives'),

    sec('4', 'Conclusion générale'),
    body("Ce projet a permis de concevoir et de développer une application de quiz pédagogiques interactifs destinée à améliorer le processus d'évaluation formative en classe. L'objectif principal était de proposer une solution numérique rendant l'évaluation plus rapide, plus motivante et plus efficace, sans dépendance à une connexion Internet."),
    body("L'application répond à ces objectifs grâce à trois éléments clés : un système de quiz en temps réel fonctionnant en réseau local, un feedback immédiat et explicatif après chaque réponse, et un système complet de statistiques pédagogiques permettant un suivi détaillé des performances des apprenants."),

    sub('4.1', 'Synthèse du projet'),
    body("Le projet repose sur trois axes principaux qui constituent sa valeur pédagogique et technique :"),
    bul("La conception d'un système de quiz interactif fonctionnant en réseau local, accessible à tous les types d'établissements sans contrainte de connectivité."),
    bul("L'amélioration de l'engagement et de la motivation des élèves grâce à la gamification (points, classement, feedback immédiat, avatars personnalisés)."),
    bul("L'exploitation pédagogique des données à travers un système de statistiques à trois niveaux : par session, par quiz et par élève."),
    body("Ces trois axes permettent de transformer une évaluation classique en une expérience interactive, dynamique et exploitable pédagogiquement. L'enseignant dispose d'un outil complet qui couvre tout le cycle de l'évaluation formative, de la préparation jusqu'à l'analyse des résultats."),

    sub('4.2', 'Difficultés rencontrées'),
    body("Durant le développement du projet, plusieurs difficultés techniques ont été rencontrées et résolues :"),
    bul("La gestion de la communication en temps réel entre le serveur et plusieurs clients simultanément, notamment la synchronisation des messages WebSockets."),
    bul("La gestion correcte des réponses simultanées : plusieurs élèves peuvent soumettre leurs réponses en même temps, ce qui nécessite un traitement concurrent fiable."),
    bul("La conception du système d'ordre aléatoire des questions par élève, garantissant que chaque élève voit toutes les questions une seule fois dans un ordre différent."),
    bul("L'organisation du système de statistiques, qui doit agréger des données issues de multiples sources de manière cohérente et performante."),
    bul("La stabilité du système sur un réseau local avec plusieurs connexions actives simultanément, notamment la gestion des déconnexions inattendues."),

    sub('4.3', 'Analyse critique (points forts et limites)'),
    miniTitle('Points forts'),
    bul("Interface simple et intuitive pour les élèves comme pour l'enseignant, ne nécessitant aucune formation préalable."),
    bul("Fonctionnement entièrement en réseau local, sans dépendance à une connexion Internet."),
    bul("Communication en temps réel fiable grâce aux WebSockets."),
    bul("Système de feedback immédiat favorisant l'apprentissage par l'erreur."),
    bul("Gamification efficace : points et classement augmentant la motivation des élèves."),
    bul("Ordre aléatoire des questions par élève, limitant les effets de copie."),
    bul("Statistiques pédagogiques détaillées et exportables (Excel et CSV)."),
    bul("Données stockées localement, sans risque de fuite vers des serveurs externes."),
    miniTitle('Limites'),
    bul("Dépendance au réseau local : la qualité du Wi-Fi influence directement les performances de l'application."),
    bul("Absence d'accès distant : l'application n'est pas accessible depuis l'extérieur du réseau local."),
    bul("Types de questions limités aux choix multiples actuellement."),
    bul("Nécessite un appareil connecté pour chaque élève."),
    bul("L'interface pourrait bénéficier d'améliorations visuelles supplémentaires."),

    sub('4.5', "Perspectives d'amélioration"),
    body("Plusieurs pistes d'amélioration peuvent être envisagées pour enrichir l'application et étendre ses capacités :"),
    bul("Développement d'une version accessible à distance via Internet, pour permettre l'utilisation en cours en ligne ou en apprentissage hybride."),
    bul("Ajout de nouveaux types de questions : réponse ouverte courte, questions avec images ou audio, questions à correspondance."),
    bul("Intégration d'un module d'intelligence artificielle pour analyser automatiquement les difficultés récurrentes et suggérer des ressources pédagogiques adaptées."),
    bul("Développement d'un mode d'apprentissage adaptatif qui ajuste la difficulté des questions en fonction du niveau de chaque élève."),
    bul("Amélioration de l'interface utilisateur pour la rendre encore plus moderne et responsive sur tous les appareils."),

    sub('4.6', 'Recommandations'),
    body("Pour une utilisation optimale de l'application en classe, les recommandations suivantes sont proposées :"),
    bul("S'assurer que le réseau Wi-Fi de la salle de classe est stable et suffisamment dimensionné pour le nombre de connexions simultanées prévues."),
    bul("Préparer et tester les quiz avant la séance pour optimiser le temps d'évaluation en classe."),
    bul("Encourager les élèves à créer leur compte dès la première session pour permettre un suivi longitudinal de leurs performances."),
    bul("Consulter régulièrement les statistiques pédagogiques après chaque session pour adapter l'enseignement en conséquence."),
    bul("Introduire l'application progressivement auprès des élèves pour les familiariser avec l'outil."),
  ];
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const children = [
    ...cover(),
    ...remerciement(),
    ...resume(),
    pb(),
    new TableOfContents('Sommaire', { hyperlink: true, headingStyleRange: '1-4' }),
    ...listeFigures(),
    ...listeTableaux(),
    ...chapter1(),
    ...chapter2(),
    ...chapter3(),
    ...chapter4(),
  ];

  const doc = new Document({
    numbering: {
      config: [{
        reference: 'bul',
        levels: [{
          level: 0,
          format: LevelFormat.BULLET,
          text: '•',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }]
      }]
    },
    styles: {
      default: { document: { run: { font: 'Arial', size: 24 } } },
      paragraphStyles: [
        {
          id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 72, bold: true, font: 'Arial', color: '2E75B6' },
          paragraph: { spacing: { before: 0, after: 240 }, alignment: AlignmentType.CENTER, outlineLevel: 0 }
        },
        {
          id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 28, bold: true, font: 'Arial', color: '1F3864' },
          paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 1 }
        },
        {
          id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 26, bold: true, font: 'Arial', color: '2E75B6' },
          paragraph: { spacing: { before: 300, after: 140 }, outlineLevel: 2 }
        },
        {
          id: 'Heading4', name: 'Heading 4', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 24, bold: true, italics: true, font: 'Arial', color: '1F3864' },
          paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 3 }
        },
      ]
    },
    sections: [{
      properties: {
        titlePage: true,
        page: {
          size: { width: PW, height: PH },
          margin: { top: MAR, right: MAR, bottom: MAR, left: MAR, header: 709, footer: 709 }
        }
      },
      headers: {
        first: new Header({ children: [new Paragraph({ children: [new TextRun('')] })] }),
        default: new Header({
          children: [new Paragraph({
            spacing: { after: 0 },
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 3 } },
            tabStops: [{ type: TabStopType.RIGHT, position: CW }],
            children: [
              run('Application de Quiz Pédagogiques Interactifs en Réseau Local',
                { size: 18, color: '777777', italics: true }),
              run('\t', { size: 18 }),
              new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '2E75B6', font: 'Arial', bold: true })
            ]
          })]
        })
      },
      footers: {
        first: new Footer({ children: [new Paragraph({ children: [new TextRun('')] })] }),
        default: new Footer({
          children: [new Paragraph({
            spacing: { after: 0 },
            border: { top: { style: BorderStyle.SINGLE, size: 2, color: 'DDDDDD', space: 3 } },
            children: [run('Rapport de projet – 2024/2025', { size: 18, color: '999999' })]
          })]
        })
      },
      children
    }]
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync('rapport_final.docx', buffer);
  console.log('rapport_final.docx genere avec succes !');
}

main().catch(console.error);
