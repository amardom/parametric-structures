"use strict";

const canvas = document.querySelector("#viewport");
const context = canvas.getContext("2d");
const renderDepth = createDepthRenderer();
const width = document.querySelector("#width");
const thickness = document.querySelector("#thickness");
const thirdParameter = document.querySelector("#third-parameter");
const parameterSelects = [width, thickness, thirdParameter];
const readout = document.querySelector("#readout");
const materialMasses = document.querySelector("#material-masses");
const legend = document.querySelector("#legend");
const scaleEnd = document.querySelector("#scale-end");
const tabs = ["plans", "cad", "result"].map((id) => document.getElementById(id));
const format = new Intl.NumberFormat("en-GB", { useGrouping: false, minimumFractionDigits: 2, maximumFractionDigits: 2 });
const openingFormat = new Intl.NumberFormat("en-GB", { useGrouping: false, minimumFractionDigits: 3, maximumFractionDigits: 3 });
const projects = {
  slab: {
    planFolder: "slab",
    title: "Slab–Column Opening",
    labels: ["Service opening"],
    options: [[["none", "No opening"], ["near", "Near column"], ["far", "300 mm farther"]]],
    selected: ["near"],
    cases: window.slabCases,
    subtitle: "Concrete flat slab · Local 3D solid FEM · 300 kN load",
    question: "How does moving the service opening change the shear around the column?",
    center: [0, -.24],
    centerX: .05,
    span: 3.2,
    viewHeight: 3.65,
    azimuth: .65,
    elevation: .33,
  },
  vierendeel: {
    planFolder: "vierendeel",
    title: "Vierendeel Cantilever",
    labels: ["Facade bay", "Post-to-chord joints"],
    options: [[[3, "3 m"], [4, "4 m"]],
              [["rigid", "Rigid"], ["flexible", "Semi-rigid"]]],
    selected: ["4", "flexible"],
    cases: window.vierendeelCases,
    subtitle: "Two steel facade frames · 12 m cantilever · Asymmetric floor loads",
    question: "How do bay width and joint stiffness affect distortion of the window opening?",
    center: [3.4, 1.7],
    centerX: 4.5,
    span: 17,
    viewHeight: 14.7,
    azimuth: .32,
    elevation: .32,
  },
  auditorium: {
    planFolder: "auditorium",
    title: "Folded Auditorium",
    labels: ["Ceiling profile", "Acoustic treatment", "Listening position"],
    options: [[["flat", "Flat"], ["folded", "Folded"]],
              [["reflective", "Hard surfaces"], ["absorptive", "Absorptive ceiling + rear wall"]],
              [["front", "Front rows"], ["middle", "Middle rows"], ["back", "Back rows"]]],
    selected: ["folded", "reflective", "middle"],
    cases: window.auditoriumCases,
    subtitle: "Speech · First reflections · Illustrative sound playback",
    question: "How do ceiling shape and absorption change what you hear at each seat?",
    center: [4.5, 2.5],
    centerX: 8.5,
    span: 19,
    viewHeight: 11,
    azimuth: -.26,
    elevation: .22,
  },
  facade: {
    planFolder: "facade",
    title: "Historic Facade",
    labels: ["Gallery width", "Construction stage"],
    options: [[[4, "4 m"], [7, "7 m"]],
              [["existing", "Existing"], ["underpinning", "Temporary supports"],
               ["excavation", "Excavation"], ["permanent", "Permanent structure"]]],
    selected: ["7", "excavation"],
    cases: window.facadeCases,
    subtitle: "Historic masonry · Underbuild sequence · Beam and spring FEM",
    question: "When does the facade move as the gallery is excavated below?",
    center: [0.7, .9],
    centerX: 7,
    span: 16,
    viewHeight: 10,
    azimuth: .34,
    elevation: .24,
  },
  cabin: {
    planFolder: "cabin",
    title: "Thermal Cabin",
    labels: ["Main window", "Solar shading"],
    options: [[["south", "South"], ["west", "West"]],
              [["open", "Unshaded"], ["shaded", "External louvres"]]],
    selected: ["west", "open"],
    cases: window.cabinCases,
    subtitle: "Insulated concrete envelope · Flat roof · Two windows",
    question: "Where can the main window face without overheating the cabin?",
    center: [0, 1.4],
    span: 7,
    viewHeight: 7.5,
    azimuth: -.62,
    elevation: .63,
  },
  atrium: {
    planFolder: "atrium",
    title: "Atrium Walkway",
    labels: ["Hanger position", "Deck depth"],
    options: [[[33, "One-third of the span"], [50, "Midspan"]],
              [[18, "180 mm"], [26, "260 mm"]]],
    selected: ["50", "18"],
    cases: window.atriumCases,
    subtitle: "Curved concrete deck · Fixed ends · One steel hanger",
    question: "How does moving the hanger change the vibration felt at the edge?",
    center: [-1.8, 2.4],
    centerX: 0,
    span: 18,
    viewHeight: 9,
    azimuth: -.36,
    elevation: .45,
    signed: true,
  },
  terrace: {
    planFolder: "terrace",
    title: "Concrete Balcony",
    labels: ["Cantilever radius", "Top reinforcement"],
    options: [[[2.5, "2.5 m"], [3.5, "3.5 m"], [4.5, "4.5 m"]],
              [[1400, "1400 mm²/m"], [2400, "2400 mm²/m"]]],
    selected: ["3.5", "1400"],
    cases: window.terraceCases,
    subtitle: "240 mm concrete slab · Fixed straight edge",
    question: "How do cantilever radius and top reinforcement affect balcony deflection?",
    center: [1.5, .42],
    span: 9,
    viewHeight: 6.4,
    azimuth: 2.76,
    warp: 5,
  },
  shelter: {
    planFolder: "shelter",
    title: "Concrete Shelter",
    labels: ["Width", "Roof slab thickness", "Rear window"],
    options: [[[12, "12 m"], [15, "15 m"]], [[30, "30 cm"], [40, "40 cm"]],
              [["original", "4.80 m · Centred"], ["wide", "7.20 m · Centred"],
               ["shifted", "7.20 m · Offset left"]]],
    selected: ["15", "30", "original"],
    cases: window.shelterCases,
    subtitle: "Self-weight · Elastic concrete · Fixed bases",
    question: "How does widening or shifting the rear window change the way the roof is supported?",
    center: [2.5, 1.45],
    azimuth: 2.66,
    viewHeight: 8.2,
  },
  gable: {
    planFolder: "gable",
    title: "Gable Frame",
    labels: ["Span between columns", "Ridge rise above eaves", "Entrance roof projection"],
    options: [[[6, "6 m"], [8, "8 m"]], [[80, "0.80 m"], [120, "1.20 m"]],
              [[0, "0 m"], [1, "1 m"], [2, "2 m"]]],
    selected: ["6", "80", "2"],
    cases: window.gableCases,
    subtitle: "Moment-resisting roof–column joints · Fixed bases",
    question: "How does the entrance overhang twist when wind lifts one corner?",
    center: [2, 1.8],
    viewHeight: 8.0,
    warp: 15,
    signed: true,
    columnSide: 0.35,
  },
  observatory: {
    planFolder: "observatory",
    title: "Observatory",
    labels: ["Interior arches", "Tube outside diameter", "Transverse arches"],
    options: [[[12, "12 arches"], [8, "8 arches"], [4, "4 arches"]],
              [[60, "Ø 60 mm"], [45, "Ø 45 mm"], [35, "Ø 35 mm"]],
              [[14, "14 arches"], [10, "10 arches"], [6, "6 arches"]]],
    selected: ["12", "60", "14"],
    cases: window.observatoryCases?.variants,
    subtitle: "Self-weight of concrete, steel and glazing",
    question: "How does reducing the steel frame affect the telescope slit width?",
    center: [0, 2.35],
    span: 5,
    viewHeight: 7.2,
    azimuth: 2.65,
    warp: 180,
  },
  house: {
    planFolder: "house",
    title: "Glass House",
    labels: ["Column setback"],
    options: [[[160, "1.60 m"], [240, "2.40 m"], [320, "3.20 m"]]],
    selected: ["240"],
    cases: window.houseCases,
    subtitle: "Concrete self-weight · Column-free glazed corner",
    question: "How does moving the column inward affect deflection at the glazed corner?",
    center: [4, 3],
    centerX: 4,
    span: 8,
    viewHeight: 11.3,
    azimuth: 2.60,
    warp: 35,
  },
  hypar: {
    planFolder: "hypar",
    title: "Steel Hypar",
    labels: ["Free-tip rise and drop", "Cantilever projection"],
    options: [[[30, "±0.30 m"], [60, "±0.60 m"]], [[3, "3 m"], [6, "6 m"]]],
    selected: ["60", "6"],
    cases: window.hyparCases,
    subtitle: "Steel shell · RHS 180 × 100 × 6 mm · Fixed root",
    question: "How do curvature and projection affect uplift at the two free tips?",
    center: [0, -1.1],
    centerX: 2.1,
    span: 9.2,
    viewHeight: 8.5,
    azimuth: 1.39,
    elevation: 0.30,
    warp: 35,
    signed: true,
  },
  bridge: {
    planFolder: "bridge",
    title: "Concrete Arch Bridge",
    labels: ["Hangers per arch", "Hanger diameter"],
    options: [[[5, "5 per arch"], [9, "9 per arch"]], [[24, "Ø24 mm"], [40, "Ø40 mm"]]],
    selected: ["9", "40"],
    cases: window.bridgeCases,
    subtitle: "Self-weight and uniform deck load (5 kPa) · Fixed abutment bases",
    question: "Where does the load go if the bridge loses a midspan hanger?",
    center: [0, 1.45],
    centerX: 12,
    span: 27,
    viewHeight: 15,
    azimuth: 0.36,
    elevation: 0.31,
    warp: 20,
    signed: true,
  },
  extension: {
    planFolder: "extension",
    title: "Roof Extension",
    labels: ["Column offset from left wall", "Transfer beam depth"],
    options: [[[150, "1.50 m"], [300, "3.00 m"]], [[450, "450 mm"], [650, "650 mm"]]],
    selected: ["150", "450"],
    cases: window.extensionCases,
    subtitle: "Steel transfer beam · Equivalent masonry supports",
    question: "Which existing wall takes more load when the new column moves?",
    center: [0, 1.55],
    centerX: 3,
    span: 6,
    viewHeight: 10.8,
    azimuth: 0.34,
    elevation: 0.21,
    warp: 40,
    signed: true,
  },
  brutalist: {
    planFolder: "brutalist",
    title: "Brutalist Housing Block",
    labels: ["Storeys", "Wall thickness design"],
    options: [[[6, "6 storeys"], [10, "10 storeys"], [14, "14 storeys"]],
              [["uniform", "Uniform baseline"], ["optimized", "Optimised"]]],
    selected: ["14", "uniform"],
    cases: window.brutalistCases?.variants,
    subtitle: "Two apartments per storey · Fixed base · Elastic shell model",
    question: "How much concrete can be saved while keeping interstorey drift within the study limit?",
    center: [0, 21],
    centerX: 0,
    span: 20,
    viewHeight: 52,
    azimuth: 0.34,
    elevation: 0.18,
    warp: 250,
    signed: true,
  },
  canopy: {
    planFolder: "canopy",
    title: "Canopy",
    labels: ["Anchor bolts", "Force per tie rod"],
    options: [[[4, "4 bolts"], [6, "6 bolts"]], [[20, "20 kN"], [40, "40 kN"]]],
    selected: ["4", "20"],
    cases: window.canopyCases?.variants,
    subtitle: canopySubtitle(window.canopyCases?.tie_angle_deg),
    question: "How do bolt count and tie-rod force affect the opening at the anchor plate?",
    center: [0.25, 1.85],
    centerX: 0,
    span: 4.3,
    viewHeight: 5.6,
    azimuth: 2.62,
    warp: 120,
  },
};
const brutalist = projects.brutalist;
const housingOptimization = document.querySelector("#housing-optimization");
const shelter = projects.shelter;
const terrace = projects.terrace;
const cabin = projects.cabin;
const facade = projects.facade;
const slab = projects.slab;
const slabResponse = document.querySelector("#slab-response");
const vierendeel = projects.vierendeel;
const vierendeelResponse = document.querySelector("#vierendeel-response");
const auditorium = projects.auditorium;
const auditoriumResponse = document.querySelector("#auditorium-response");
const auditoriumPlay = document.querySelector("#auditorium-play");
const auditoriumCompare = document.querySelector("#auditorium-compare");
const auditoriumAudioStatus = document.querySelector("#auditorium-audio-status");
let auditoriumAudio, auditoriumActiveButton;
let auditoriumPlayback = 0;
const facadeResponse = document.querySelector("#facade-response");
const cabinControls = document.querySelector("#cabin-controls");
const cabinResponse = document.querySelector("#cabin-response");
const cabinHour = document.querySelector("#cabin-hour");
const cabinField = document.querySelector("#cabin-field");
const cabinChart = document.querySelector("#cabin-chart");
let cabinVariant;
const atrium = projects.atrium;
const atriumResponse = document.querySelector("#atrium-response");
const atriumFrequency = document.querySelector("#atrium-frequency");
const atriumAnimation = document.querySelector("#atrium-animation");
const atriumChart = document.querySelector("#atrium-chart");
let atriumFrame = 0;
let atriumState;
const terraceCracking = document.querySelector("#terrace-cracking");
const terraceCrackingMap = document.querySelector("#terrace-cracking-map");
const shelterReactions = document.querySelector("#shelter-reactions");
const shelterWindowComparison = document.querySelector("#shelter-window-comparison");
const gable = projects.gable;
const gableLoad = document.querySelector("#gable-load");
const gableReactions = document.querySelector("#gable-reactions");
const observatory = projects.observatory;
const house = projects.house;
const canopy = projects.canopy;
const hypar = projects.hypar;
const bridge = projects.bridge;
const bridgeCondition = document.querySelector("#bridge-condition");
const hangerLossReadout = document.querySelector("#hanger-loss-readout");
const hangerChangeLimit = Math.max(10, Math.ceil(Math.max(0, ...Object.values(bridge.cases ?? {}).flatMap(
  variant => (variant.loss?.hanger_changes_kn ?? []).map(Math.abs))) / 10) * 10);
const extension = projects.extension;
const extensionStudy = document.querySelector("#extension-study");
const extensionDetails = window.extensionDetails;
const wallReactions = document.querySelector("#wall-reactions");
const hyparLoad = document.querySelector("#hypar-load");
const hyparUpliftNote = document.querySelector("#hypar-uplift-note");
const boltForces = document.querySelector("#bolt-forces");
const houseRenderMeshes = new WeakMap();
const sweep = window.observatoryCases;
let project;
let colorLimit;
const solidColors = { audPanel: [105, 165, 151], slabCut: [0, 132, 123], slabEast: [130, 90, 151], slabContext: [221, 222, 215], slabPlinth: [177, 164, 143], slabDuct: [82, 119, 136], slabOpening: [47, 103, 151], slabConcrete: [200, 192, 171], vierCore: [172, 163, 143], vierGround: [218, 216, 204], vierSteel: [62, 82, 83], vierDeck: [196, 193, 177], vierFloor: [116, 127, 123], vierWindow: [214, 113, 39], audSeat: [74, 115, 110], audDirect: [24, 162, 126], audCeiling: [241, 136, 59], audRear: [157, 101, 208], audOther: [138, 147, 151], facadeStone: [216, 195, 164], facadeGlass: [77, 97, 104], facadeFooting: [157, 166, 165], facadeSoil: [164, 134, 105], facadeProp: [138, 80, 57], facadeGaugeA: [37, 100, 180], facadeGaugeB: [188, 47, 44], hyparDoor: [77, 83, 79], hyparFrame: [35, 37, 37], housingGlass: [71, 81, 81], emblem: [149, 58, 39], emblemHammer: [166, 65, 43], emblemBacking: [177, 172, 159], timber: [192, 158, 117], wall: [177, 172, 159], roof: [213, 209, 195], glass: [115, 174, 181], steel: [68, 85, 88], column: [176, 153, 133], door: [64, 125, 138], anchor: [159, 88, 65] };
const colorRamp = [[211, 225, 220], [65, 119, 131], [203, 126, 73]];
const initialCamera = { azimuth: 0.40, elevation: 0.42, zoom: 1 };

let camera = { ...initialCamera };
let mode = "plans";
let drawing = "plan";
const planView = document.querySelector("#plan-view");
const planSheet = document.querySelector("#plan-sheet");
const planLink = document.querySelector("#plan-link");
const planMissing = document.querySelector("#plan-missing");
const drawingButtons = [...planView.querySelectorAll("button[data-drawing]")];
const view3d = document.querySelector(".viewer");
const caption = document.querySelector(".caption");
let parts = [];
let framePending = false;
let pointer = null;

function selectProject() {
  const route = location.hash.slice(1);
  const key = Object.hasOwn(projects, route) ? route : "shelter";
  project = projects[key];
  document.querySelector("h1").textContent = project.title;
  document.querySelector("#case-subtitle").textContent = project.subtitle;
  document.querySelector("#case-question").textContent = project.question;
  document.title = "Parametric Structures · " + project.title;
  document.querySelector("#width-label").textContent = project.labels[0];
  document.querySelector("#option-label").textContent = project.labels[1] ?? "";
  document.querySelector("#third-parameter-label").textContent = project.labels[2] ?? "";
  document.querySelectorAll("nav a").forEach((link) => {
    if (link.hash === "#" + key) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  });
  parameterSelects.forEach((select, index) => {
    select.closest("label").hidden = index >= project.options.length;
    select.replaceChildren(...(project.options[index] ?? []).map(([value, label]) => new Option(label, value)));
    select.value = project.selected[index];
  });
  const maxDrop = Math.max(0, ...Object.values(project.cases ?? {}).map(({ result, gravity, wind, loss }) => Math.max(result?.max_abs_mm ?? result?.front_mm ?? 0,
    gravity?.front_mm ?? 0, wind?.max_abs_mm ?? 0, loss?.front_mm ?? 0)));
  const colorStep = project === canopy ? 0.01 : project === observatory ? 0.25 : 2;
  colorLimit = Math.max(colorStep, Math.ceil(maxDrop / colorStep) * colorStep);
  resetCamera();
  selectVariant();
}

function selectVariant() {
  project.selected = parameterSelects.slice(0, project.options.length).map(select => select.value);
  const key = project.selected.join("-");
  const variant = project.cases?.[key];
  const showingPlans = mode === "plans";
  stopAtriumAnimation();
  stopAuditoriumAudio();
  slabResponse.hidden = project !== slab || mode !== "result" || !variant;
  document.querySelector("#slab-geometry-note").hidden = project !== slab || mode !== "cad" || !variant;
  vierendeelResponse.hidden = project !== vierendeel || mode !== "result" || !variant;
  auditoriumResponse.hidden = project !== auditorium || mode !== "result" || !variant;
  facadeResponse.hidden = project !== facade || mode !== "result" || !variant;
  cabinResponse.hidden = project !== cabin || mode !== "result" || !variant;
  cabinControls.hidden = cabinResponse.hidden;
  atriumResponse.hidden = project !== atrium || mode !== "result" || !variant;
  document.querySelector("#atrium-controls").hidden = atriumResponse.hidden;
  terraceCracking.hidden = project !== terrace || mode !== "result" || !variant;
  if (!terraceCracking.hidden) terraceCrackingMap.src = `plans/terrace/${key}-cracking.svg`;
  housingOptimization.hidden = project !== brutalist || mode !== "result" || !variant;
  if (!housingOptimization.hidden) showHousingOptimization(variant);
  const bridgeStudy = project === bridge && mode === "result" && Boolean(variant?.loss);
  bridgeCondition.closest("label").hidden = !bridgeStudy;
  const hangerLoss = bridgeStudy && bridgeCondition.value === "loss";
  document.querySelector("#hanger-loss-comparison").hidden = !hangerLoss;
  const extensionResults = project === extension && mode === "result" && Boolean(extensionDetails);
  extensionStudy.closest("label").hidden = !extensionResults;
  const connection = extensionResults ? extensionDetails.cases[extensionStudy.value] : undefined;
  for (const [index, select] of parameterSelects.entries()) {
    select.closest("label").hidden = Boolean(connection) || index >= project.options.length;
  }
  document.querySelector("#connection-caption").hidden = !connection;
  document.querySelector("#connection-assumptions").hidden = !connection;
  gableLoad.closest("label").hidden = project !== gable || mode !== "result" || !variant?.wind;
  shelterReactions.hidden = project !== shelter || mode !== "result" || !variant;
  document.querySelector("#house-deflection-note").hidden = project !== house || mode !== "result" || !variant;
  document.querySelector("#canopy-anchor-note").hidden = project !== canopy || mode !== "result" || !variant;
  shelterWindowComparison.hidden = shelterReactions.hidden;
  gableReactions.hidden = project !== gable || mode !== "result" || !variant;
  document.querySelector("#observatory-glazing-note").hidden = project !== observatory || mode !== "result" || !variant;
  document.querySelector("#gable-uplift-note").hidden = gableReactions.hidden;
  hyparLoad.closest("label").hidden = project !== hypar || mode !== "result" || !variant;
  hyparUpliftNote.hidden = hyparLoad.closest("label").hidden || hyparLoad.value !== "wind" || !variant?.uplift_pa;
  tabs.forEach((tab) => tab.setAttribute("aria-pressed", String(tab.id === mode)));
  document.querySelector("#cad").textContent = project === slab ? "Solid Geometry" : project === vierendeel ? "Frame Geometry" : project === facade || project === auditorium ? "Section Geometry" : "STEP Geometry";
  document.querySelector("#result").textContent = project === slab ? "Shear Transfer" : project === auditorium ? "Acoustic Response" : project === facade ? "Stage Response" : project === atrium ? "Harmonic Response" : project === cabin ? "Thermal Response" : "FE Deformed Shape";
  planView.hidden = !showingPlans;
  view3d.hidden = showingPlans || !variant;
  caption.hidden = mode !== "result" || !variant || Boolean(connection);
  readout.hidden = showingPlans || (mode !== "result" && Boolean(variant));
  boltForces.hidden = true;
  wallReactions.hidden = project !== extension || mode !== "result" || !variant || Boolean(connection);
  const masses = variant?.material_masses_kg;
  materialMasses.hidden = mode !== "result" || !masses || Boolean(connection) || hangerLoss;
  if (!materialMasses.hidden) {
    const amounts = Object.entries(masses).map(([material, kilograms]) => material + " " + format.format(kilograms) + " kg");
    if (project === observatory) {
      const reference = project.cases[sweep.baseline].result.mass_kg;
      const saving = 100 * (1 - masses.Steel / reference);
      if (Math.abs(saving) >= 0.005) {
        amounts[0] += " (" + format.format(Math.abs(saving)) + (saving > 0 ? "% less than baseline)" : "% more than baseline)");
      }
    }
    materialMasses.textContent = "Modelled material mass · " + amounts.join(" · ");
  }
  if (showingPlans) {
    showPlan();
    return;
  }
  if (!variant) {
    readout.textContent = "Generate viewer data with .venv/bin/python website/build_data.py";
    return;
  }
  if (project === slab) {
    caption.hidden = true;
    parts = mode === "result" ? variant.result.parts.map(smoothSlabCut) : variant.cad;
    if (mode === "result") {
      const result = variant.result;
      readout.textContent = "Column reaction " + format.format(result.reaction_kn)
        + " kN · Vertical shear crossing the cut " + format.format(result.shear_kn) + " kN";
      const labels = ["West", "East · Violet edge", "South", "North"];
      document.querySelector("#slab-cut-reading").textContent = {
        none: "With no opening, each side carries 25% of the shear crossing the cut.",
        near: "The near opening interrupts the east face of the cut and produces the strongest local concentration.",
        far: "The far opening lies outside the cut. The east side carries a slightly smaller share than with the near opening, while the local concentration is lower.",
      }[key];
      const baseline = slab.cases.none.result.shares;
      document.querySelector("#slab-shares").replaceChildren(...result.shares.map((share, i) => {
        const row = document.createElement("tr");
        const heading = document.createElement("th");
        heading.scope = "row";
        heading.textContent = labels[i];
        row.append(heading);
        const delta = share - baseline[i];
        row.insertCell().textContent = format.format(share) + "%"
          + (Math.abs(delta) >= .05 ? " (" + (delta < 0 ? "−" : "+") + format.format(Math.abs(delta)) + " pp)" : "");
        return row;
      }));
    }
    requestFrame();
    return;
  }
  if (project === vierendeel) {
    caption.hidden = true;
    parts = mode === "result" ? variant.result.parts : variant.cad;
    if (mode === "result") showVierendeel(variant.result);
    requestFrame();
    return;
  }
  if (project === auditorium) {
    caption.hidden = true;
    parts = mode === "result" ? [...variant.cad, ...variant.result.parts] : variant.cad;
    if (mode === "result") {
      const result = variant.result;
      const rear = result.paths.find(path => path.kind === "rear wall");
      const direct = result.paths[0];
      const ceiling = result.paths.filter(path => path.kind === "ceiling");
      document.querySelector("#auditorium-ceiling").textContent = ceiling.length
        ? "First ceiling reflection +" + Math.round(ceiling[0].delay_ms) + " ms after direct sound."
        : "No first-order ceiling reflection reaches this seat.";
      resetAuditoriumButtons();
      readout.textContent = "Estimated mid-band reverberation " + format.format(result.rt60_s) + " s"
        + (rear ? " · Rear reflection +" + Math.round(rear.delay_ms) + " ms" : "");
      document.querySelector("#auditorium-rear").textContent = rear
        ? "Rear-wall reflection " + Math.round(20 * Math.log10(rear.gain / direct.gain))
          + " dB relative to the direct sound."
        : "The centreline model found no first-order rear-wall reflection at this seat.";
      document.querySelector("#auditorium-section").src = "plans/auditorium/" + key + "-section.svg";
    }
    requestFrame();
    return;
  }
  if (project === facade) {
    caption.hidden = true;
    parts = mode === "result" ? variant.result.parts : variant.cad;
    if (mode === "result") {
      const result = variant.result;
      const movement = mm => (Math.abs(mm) < .005 ? "" : mm < 0 ? "↑ " : "↓ ")
        + format.format(Math.abs(mm)) + " mm";
      readout.textContent = "Differential settlement A–B · " + format.format(result.difference_mm)
        + " mm · A " + movement(result.a_mm) + " · B " + movement(result.b_mm);
      document.querySelector("#facade-stage-note").textContent = thickness.value === "permanent"
        ? result.note + " The permanent structure takes load after settlement has already accumulated during excavation."
        : result.note;
      const rows = result.history.map((entry, index) => {
        const row = document.createElement("tr");
        const heading = document.createElement("th");
        heading.scope = "row";
        heading.textContent = facade.options[1][index][1];
        if (facade.options[1][index][0] === thickness.value) row.setAttribute("aria-current", "step");
        row.append(heading);
        row.insertCell().textContent = format.format(entry.difference_mm) + " mm";
        return row;
      });
      document.querySelector("#facade-history").replaceChildren(...rows);
    }
    requestFrame();
    return;
  }
  if (project === cabin) {
    caption.hidden = true;
    if (mode === "result") {
      cabinVariant = variant;
      showCabinHour();
    } else {
      parts = variant.cad;
    }
    requestFrame();
    return;
  }
  if (project === atrium) {
    caption.hidden = true;
    if (mode === "result") showAtriumResponse(variant);
    else parts = variant.cad;
    requestFrame();
    return;
  }
  if (connection) {
    showExtensionDetail(connection);
    requestFrame();
    return;
  }
  const result = project === hypar && hyparLoad.value === "gravity"
    ? { ...variant.result, ...variant.gravity }
    : project === gable && variant.wind && gableLoad.value === "wind"
      ? { ...variant.result, ...variant.wind }
      : hangerLoss ? { ...variant.result, ...variant.loss } : variant.result;
  if (project === observatory) {
    showObservatory(result);
  } else if (project === canopy) {
    showCanopy(variant);
  } else if (mode === "cad") {
    parts = project === house ? houseCadMesh(variant.cad) : variant.cad;
  } else {
    const points = result.points.map((value, i) => value + result.displacement[i] * (project.warp ?? 80) / 1000);
    const axis = project === brutalist ? 1 : 2;
    const vertical = result.displacement.filter((_, i) => i % 3 === axis)
      .map(value => project === brutalist ? -value : value);
    if (project === brutalist) {
      parts = [...housingDeformedMeshes(points, result, vertical),
               ...deformedHousingEmblem(variant.cad, result.points, points)];
    } else if (project === terrace) {
      const half = variant.geometry.slab_thickness_m / 2;
      const lower = points.map((value, i) => i % 3 === 2 ? value - half : value);
      const upper = points.map((value, i) => i % 3 === 2 ? value + half : value);
      const context = variant.cad.filter(part => part.material !== "roof").map(part => {
        if (!part.attachment) return part;
        const moved = part.points.map((coordinate, index) => {
          const [a, b, weight] = part.attachment[Math.floor(index / 3)];
          const axis = index % 3;
          const delta = result.displacement[3 * a + axis] * (1 - weight)
            + result.displacement[3 * b + axis] * weight;
          return coordinate + delta * terrace.warp / 1000;
        });
        return { ...part, points: moved };
      });
      parts = [...context, closeShell(lower, upper, result.faces, vertical)];
    } else if (project === shelter) {
      parts = shelterDeformedMeshes(points, result, vertical, variant.cad);
    } else if (project === gable) {
      const roofFaces = result.faces.filter((face) => face.length > 2);
      const slope = (Number(thickness.value) / 100) / (Number(width.value) / 2);
      const roof = thickenGableRoof(points, result.points, roofFaces, vertical, variant.cad, slope, result.faces);
      parts = [roof, squareColumnMesh(points, result.faces, vertical, gable.columnSide, roof.soffits)];
    } else if (project === house) {
      parts = houseDeformedMeshes(points, result, vertical, variant.cad);
    } else if (project === extension) {
      parts = extensionDeformedMeshes(points, result, vertical, variant);
    } else if (project === bridge) {
      parts = bridgeDeformedMeshes(points, result, vertical, variant.geometry);
    } else if (project === hypar) {
      const shell = result.faces.filter(face => face.length === 4);
      const edges = result.faces.filter(face => face.length === 2);
      parts = [...variant.cad.filter(part => ["wall", "hyparDoor"].includes(part.material)),
               { points, faces: shell, vertical },
               hyparFrameMesh(points, edges, variant.geometry)];
    } else {
      parts = [{ points, faces: result.faces, vertical }];
    }
  }
  legend.hidden = mode !== "result";
  scaleEnd.textContent = project === canopy ? format.format(colorLimit) : String(colorLimit);
  document.querySelector("#legend-label").textContent = project === brutalist ? "Actual wind-axis displacement"
    : project === canopy ? "Actual displacement" : "Actual vertical deflection";
  legend.classList.toggle("signed", project === house || project.signed);
  document.querySelector("#scale-start").textContent = project === house || project.signed ? "−" + scaleEnd.textContent : "0";
  document.querySelector("#warp-factor").textContent = project.warp ?? 80;
  if (project === house) {
    const motion = (mm) => format.format(Math.abs(mm)) + " mm " + (mm < 0 ? "↑" : "↓");
    readout.textContent = "Floor slab corner " + motion(result.floor_corner_mm)
      + " · Roof corner " + motion(result.roof_corner_mm)
      + " · Above the door " + motion(result.door_mm);
  } else if (project === terrace) {
    const low = terrace.cases[`${width.value}-1400`].result.front_mm;
    const high = terrace.cases[`${width.value}-2400`].result.front_mm;
    readout.textContent = "Maximum free-edge deflection " + format.format(result.front_mm)
      + " mm ↓ · " + format.format(100 * (1 - high / low)) + "% lower with 2400 mm²/m at this radius";
  } else if (project === shelter) {
    const force = result.wall_reactions_kn;
    const total = force.reduce((sum, value) => sum + value, 0);
    const reaction = index => format.format(force[index]) + " kN (" + Math.round(100 * force[index] / total) + "%)";
    shelterReactions.textContent = "Vertical wall base reactions · Left " + reaction(0)
      + " · Rear " + reaction(2) + " · Right " + reaction(1);
    const prefix = project.selected.slice(0, 2).join("-");
    const [original, wide, shifted] = ["original", "wide", "shifted"]
      .map(opening => shelter.cases[prefix + "-" + opening].result);
    const leftShare = ({ wall_reactions_kn: reactions }) =>
      Math.round(100 * reactions[0] / reactions.reduce((sum, value) => sum + value, 0));
    shelterWindowComparison.textContent = "Widening the window increases the roof deflection above it from "
      + format.format(original.window_mm) + " to " + format.format(wide.window_mm)
      + " mm. Shifting the wider window left raises the left wall’s share of the vertical reaction from "
      + leftShare(wide) + "% to " + leftShare(shifted) + "%.";
    readout.textContent = "Maximum roof deflection above window " + format.format(result.window_mm)
      + " mm ↓ · Front edge " + format.format(result.front_mm) + " mm ↓";
  } else if (project === gable) {
    const motion = (mm) => format.format(Math.abs(mm)) + " mm " + (mm < 0 ? "↓" : "↑");
    const [left, right] = result.tip_mm;
    const wind = variant.wind && gableLoad.value === "wind";
    const load = wind ? "Illustrative uplift " + format.format(variant.uplift_pa / 1000) + " kPa · " : "Self-weight · ";
    readout.textContent = load + "Entrance corner movements, left " + motion(left) + ", right " + motion(right)
      + " · Difference " + format.format(Math.abs(left - right)) + " mm"
      + " · Peak vertical movement " + format.format(result.max_abs_mm) + " mm";
    document.querySelector("#gable-uplift-note").textContent = variant.wind
      ? "The wind case applies " + variant.uplift_pa / 1000 + " kPa of illustrative uplift to the corner zone marked on the plan."
      : "With no entrance overhang, there is no corner zone for the illustrative wind load.";
    const reactions = result.reactions_kn.map(kn => format.format(kn) + " kN");
    gableReactions.textContent = "Vertical base reactions, left / right · Entrance " + reactions.slice(0,2).join(" / ")
      + " · Rear " + reactions.slice(2).join(" / ");
  } else if (project === hypar) {
    const motion = (mm) => format.format(Math.abs(mm)) + " mm " + (mm < 0 ? "↓" : "↑");
    const [low, high] = result.tips_mm;
    const moment = result.wall_moment_knm;
    const direction = moment < 0 ? "downward" : "uplift";
    readout.textContent = "Low tip " + motion(low) + " · High tip " + motion(high)
      + " · Differential movement " + format.format(Math.abs(high - low)) + " mm"
      + " · Wall moment " + format.format(Math.abs(moment)) + " kN·m (" + direction + ")";
    if (!hyparUpliftNote.hidden) {
      const [left, right] = variant.uplift_pa.map(pressure => format.format(pressure / 1000));
      const projection = thickness.value;
      const [shallow, steep] = [30, 60].map(rise => hypar.cases[rise + "-" + projection].result.tips_mm[1]);
      hyparUpliftNote.textContent = "Both shapes use the same illustrative uplift of " + left + " kPa on the left zone and "
        + right + " kPa on the right. At " + projection + " m projection, the high tip rises "
        + format.format(shallow) + " mm at ±0.30 m and " + format.format(steep) + " mm at ±0.60 m.";
    }
  } else if (project === bridge) {
    readout.textContent = "Maximum deck deflection " + format.format(result.deck_mm)
      + " mm ↓ · Maximum hanger tension " + format.format(result.hanger_kn) + " kN";
    if (hangerLoss) {
      const intact = variant.result;
      const rows = [
        ["Maximum deck deflection (mm)", intact.deck_mm, result.deck_mm],
        ["Midspan deck edge difference (mm)", intact.edge_difference_mm, result.edge_difference_mm],
        ["Maximum remaining hanger tension (kN)", intact.hanger_kn, result.hanger_kn],
        ["Removed hanger tension (kN)", result.removed_hanger_kn, null],
      ];
      document.querySelector("#hanger-loss-values").replaceChildren(...rows.map(([label, before, after]) => {
        const row = document.createElement("tr");
        const heading = document.createElement("th");
        heading.scope = "row";
        heading.textContent = label;
        row.append(heading);
        row.insertCell().textContent = format.format(before);
        row.insertCell().textContent = after === null ? "—" : format.format(after);
        return row;
      }));
      const change = Math.max(...result.hanger_changes_kn);
      const opposite = result.opposite_arch_change_kn;
      readout.hidden = true;
      const net = (opposite >= 0 ? "+" : "−") + format.format(Math.abs(opposite));
      hangerLossReadout.textContent = "Largest tension increase +" + format.format(change)
        + " kN · Net change on opposite arch " + net + " kN"
        + " · Hanger colours show tension change (blue decrease, red increase, scale ±" + hangerChangeLimit + " kN)";
    }
  } else if (project === brutalist) {
    const drift = 1000 * Math.max(...result.drifts.map(Math.abs));
    readout.textContent = "Roof movement " + format.format(result.roof_mm) + " mm · Peak interstorey drift "
      + openingFormat.format(drift) + " ‰";
  } else if (project === extension) {
    const [left, right] = result.wall_reactions_kn;
    const share = Math.round(100 * left / (left + right));
    wallReactions.querySelector("#left-wall-reaction").textContent = "Left wall " + format.format(left) + " kN · " + share + "%";
    wallReactions.querySelector("#right-wall-reaction").textContent = "Right wall " + format.format(right) + " kN · " + (100 - share) + "%";
    wallReactions.querySelector(".wall-reaction-bar span").style.width = share + "%";
    readout.textContent = "Column load " + variant.column_force_kn + " kN · Deflection at column " + format.format(result.seat_mm) + " mm ↓";
  } else if (project !== observatory && project !== canopy) {
    readout.innerHTML = "<strong>" + format.format(result.front_mm) + " mm</strong> maximum deflection " + project.location + ".";
  }
  requestFrame();
}

function showVierendeel(result) {
  const [near, far] = result.tip_mm;
  const [a, b] = result.diagonal_changes_mm;
  const signed = value => (value >= 0 ? "+" : "−") + format.format(Math.abs(value)) + " mm";
  readout.textContent = "Tip deflection ↓ " + format.format(near) + " mm near side · "
    + format.format(far) + " mm far side";
  document.querySelector("#vierendeel-diagonals").textContent =
    "Diagonal change · A " + signed(a) + " · B " + signed(b);
  const points = result.window_initial;
  const deformed = points.map(([x, z], i) => [
    x + 60 * result.window_displacement[i][0], z + 60 * result.window_displacement[i][1],
  ]);
  const onScreen = ([x,z]) => [76 + 62 * x, 257 - 62 * z];
  const polygon = positions => positions.map(point => onScreen(point).join(",")).join(" ");
  const diagonals = [[0,2],[1,3]].map(([start,end],i) => {
    const [x1,y1] = onScreen(deformed[start]);
    const [x2,y2] = onScreen(deformed[end]);
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2
      + '" stroke="#a35222"/><text x="' + (x2 + (i ? -22 : 9)) + '" y="' + (y2 - 6)
      + '" font-family="Arial" font-size="15" fill="#7c481f">' + (i ? "B" : "A") + "</text>";
  }).join("");
  document.querySelector("#vierendeel-window").innerHTML =
    '<rect width="510" height="310" fill="#f0efe8"/><polygon points="' + polygon(deformed)
    + '" fill="#f5dfbf" stroke="#a35222" stroke-width="2"/><polygon points="' + polygon(points)
    + '" fill="none" stroke="#666e71" stroke-width="2" stroke-dasharray="6 4"/>' + diagonals;
}

function resetAuditoriumButtons() {
  for (const button of [auditoriumPlay, auditoriumCompare]) {
    if (!button.dataset.wall) continue;
    button.textContent = button.dataset.wall === "reflective" ? "Play hard room" : "Play treated room";
    button.setAttribute("aria-pressed", "false");
  }
}

function stopAuditoriumAudio() {
  auditoriumPlayback++;
  auditoriumAudio?.pause();
  auditoriumAudio = undefined;
  auditoriumActiveButton = undefined;
  resetAuditoriumButtons();
  auditoriumAudioStatus.textContent = "";
}

async function playAuditorium(button) {
  const alreadyPlaying = auditoriumActiveButton === button;
  stopAuditoriumAudio();
  if (alreadyPlaying) return;
  if (thickness.value !== button.dataset.wall) {
    thickness.value = button.dataset.wall;
    selectVariant();
  }
  const playback = auditoriumPlayback;
  const [roof, , seat] = project.selected;
  const variant = auditorium.cases[[roof, button.dataset.wall, seat].join("-")];
  const clip = variant?.result.audio_mp3;
  if (!clip) {
    auditoriumAudioStatus.textContent = "Audio data is missing. Rebuild the auditorium web assets.";
    return;
  }
  const audio = new Audio("data:audio/mpeg;base64," + clip);
  auditoriumAudio = audio;
  auditoriumActiveButton = button;
  button.textContent = "Stop";
  button.setAttribute("aria-pressed", "true");
  audio.addEventListener("ended", () => {
    if (playback === auditoriumPlayback) stopAuditoriumAudio();
  }, { once: true });
  try {
    await audio.play();
  } catch {
    if (playback !== auditoriumPlayback) return;
    stopAuditoriumAudio();
    auditoriumAudioStatus.textContent = "Playback failed in this browser. Try again or open the local site in Chromium.";
  }
}

auditoriumPlay.addEventListener("click", () => playAuditorium(auditoriumPlay));
auditoriumCompare.addEventListener("click", () => playAuditorium(auditoriumCompare));

function cabinTime(hour) {
  const day = Math.min(3, Math.floor(hour / 24) + 1);
  const clock = hour === 72 ? "24" : String(hour % 24).padStart(2, "0");
  return "Day " + day + " · " + clock + ":00";
}

function drawCabinChart(frame) {
  const otherFace = width.value === "south" ? "west" : "south";
  const otherShade = thickness.value === "open" ? "shaded" : "open";
  const rotated = cabin.cases[otherFace + "-" + thickness.value];
  const shading = cabin.cases[width.value + "-" + otherShade];
  const all = Object.values(cabin.cases).flatMap(variant => variant.frames.flatMap(item => [item.air,item.outdoor]));
  const step = 4;
  const bottom = 214;
  const low = Math.floor(Math.min(...all) / step) * step;
  const high = Math.ceil(Math.max(...all) / step) * step;
  const x = hour => 57 + 631 * hour / 72;
  const y = value => bottom - 180 * (value - low) / (high - low);
  const points = (frames, key) => frames.map(item => x(item.hour).toFixed(2) + "," + y(item[key]).toFixed(2)).join(" ");
  const grid = [];
  for (let value = low; value <= high; value += step) {
    const py = y(value);
    grid.push(`<path d="M57 ${py}H688" stroke="#dce0db"/><text x="47" y="${py+4}" text-anchor="end">${value}</text>`);
  }
  cabinChart.innerHTML = `
    <rect width="720" height="305" fill="#f9f8f3"/>
    <g font-family="Arial,sans-serif" font-size="13" fill="#26383b">
      <text x="57" y="21">Temperature (°C)</text>
      ${grid.join("")}
      <path d="M57 34V214H688" fill="none" stroke="#778888"/>
      ${[24,48].map(hour => `<path d="M${x(hour)} 34V214" stroke="#d0d8d3"/>`).join("")}
      ${[12,36,60].map((hour,i) => `<text x="${x(hour)}" y="234" text-anchor="middle">Day ${i+1}</text>`).join("")}
      <polyline points="${points(cabinVariant.frames,"outdoor")}" fill="none" stroke="#8d9995" stroke-width="1.4"/>
      <polyline points="${points(rotated.frames,"air")}" fill="none" stroke="#8b553e" stroke-width="2" stroke-dasharray="7 4"/>
      <polyline points="${points(shading.frames,"air")}" fill="none" stroke="#395e80" stroke-width="2" stroke-dasharray="2 4"/>
      <polyline points="${points(cabinVariant.frames,"air")}" fill="none" stroke="#13746d" stroke-width="2.7"/>
      <path d="M${x(frame.hour)} 34V214" stroke="#526764" stroke-dasharray="3 3"/>
      <circle cx="${x(frame.hour)}" cy="${y(frame.air)}" r="4" fill="#13746d"/>
      <path d="M57 257h24" stroke="#13746d" stroke-width="2.7"/><text x="88" y="261">Selected interior</text>
      <path d="M310 257h24" stroke="#8d9995" stroke-width="1.4"/><text x="341" y="261">Outdoor air</text>
      <path d="M57 280h24" stroke="#8b553e" stroke-width="2" stroke-dasharray="7 4"/>
      <text x="88" y="284">${otherFace === "south" ? "South" : "West"} window · same shading</text>
      <path d="M310 280h24" stroke="#395e80" stroke-width="2" stroke-dasharray="2 4"/>
      <text x="341" y="284">${otherShade === "open" ? "Unshaded" : "External louvres"} · same orientation</text>
    </g>`;
}

function showCabinHour() {
  if (cabinResponse.hidden) return;
  const frame = cabinVariant.frames[Number(cabinHour.value)];
  const field = cabinField.value;
  const solar = field === "solar";
  const [minimum, maximum, units, ramp] = solar
    ? [0, 900, "W/m²", [[227, 233, 235], [78, 169, 191], [239, 209, 86], [224, 100, 39]]]
    : [24, 30, "°C", [[33, 82, 176], [0, 149, 186], [255, 168, 22], [212, 25, 46]]];
  const colour = value => {
    const ratio = Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum)));
    const position = ratio * (ramp.length - 1);
    const index = Math.min(ramp.length - 2, Math.floor(position));
    return ramp[index].map((channel, i) => channel
      + (position - index) * (ramp[index + 1][i] - channel));
  };
  document.querySelector("#cabin-scale-min").textContent = minimum;
  document.querySelector("#cabin-scale-max").textContent = maximum + " " + units;
  document.querySelector("#cabin-scale i").style.background =
    `linear-gradient(90deg, ${ramp.map(rgb => "rgb(" + rgb.join(",") + ")").join(", ")})`;
  parts = cabinVariant.cad.filter(part => solar || part.surface !== "roof").map(part =>
    part.surface ? { ...part, color: colour(frame[field][part.surface]) } : part);
  document.querySelector("#cabin-time").textContent = cabinTime(frame.hour);
  const faces = ["south","west","north","east","roof"];
  const label = face => face[0].toUpperCase() + face.slice(1);
  const values = faces.map(face => label(face) + " " + Math.round(frame[field][face])
    + (solar ? " W/m²" : " °C"));
  document.querySelector("#cabin-reading").textContent = "Indoor " + format.format(frame.air)
    + " °C · Outdoor " + format.format(frame.outdoor) + " °C · Solar gain through glass " + Math.round(frame.gain)
    + " W · " + values.join(" · ");
  const peak = cabinVariant.peak;
  const peakValue = document.createElement("strong");
  peakValue.textContent = format.format(peak.air) + " °C";
  readout.replaceChildren("Peak indoor temperature ", peakValue, " · " + cabinTime(peak.hour));
  drawCabinChart(frame);
  requestFrame();
}

cabinHour.addEventListener("input", showCabinHour);
cabinField.addEventListener("change", showCabinHour);

function stopAtriumAnimation() {
  cancelAnimationFrame(atriumFrame);
  atriumFrame = 0;
  atriumAnimation.setAttribute("aria-pressed", "false");
  atriumAnimation.textContent = "Play vibration";
}

function showAtriumResponse({ result, cad }) {
  atriumState = { result, context: cad.filter(part => part.fixed || part.attachment || part.socket) };
  atriumFrequency.replaceChildren(...result.peaks.map(({ frequency }, index) =>
    new Option(format.format(frequency) + " Hz", index)));
  const strongest = result.peaks[0];
  readout.textContent = "Highest acceleration in sweep " + format.format(strongest.acceleration)
    + " m/s² at " + format.format(strongest.frequency) + " Hz · Guardrail mass " + format.format(result.guard_mass_kg) + " kg";
  selectAtriumFrequency();
}

function drawAtriumChart(result, peak) {
  const otherStation = width.value === "50" ? "33" : "50";
  const other = atrium.cases[otherStation + "-" + thickness.value].result;
  const minFrequency = result.sweep[0][0];
  const maxFrequency = result.sweep.at(-1)[0];
  const maxResponse = Math.max(...Object.values(atrium.cases).map(({ result }) => result.peaks[0].acceleration));
  const step = 10 ** Math.floor(Math.log10(maxResponse)) / 2;
  const limit = Math.ceil(maxResponse / step) * step;
  const x = frequency => 68 + 584 * (frequency - minFrequency) / (maxFrequency - minFrequency);
  const y = value => 226 - 191 * value / limit;
  const points = sweep => sweep.map(([freq, response]) => x(freq).toFixed(2) + "," + y(response).toFixed(2)).join(" ");
  const grid = Array.from({ length: 5 }, (_, i) => {
    const value = limit * i / 4;
    const yy = y(value);
    return `<path d="M68 ${yy}H652" stroke="#d5dbd6"/><text x="58" y="${yy + 4}" text-anchor="end">${format.format(value)}</text>`;
  }).join("");
  const ticks = Array.from({ length: 6 }, (_, i) => {
    const freq = minFrequency + (maxFrequency - minFrequency) * i / 5;
    return `<text x="${x(freq)}" y="246" text-anchor="middle">${freq}</text>`;
  }).join("");
  atriumChart.innerHTML = `
    <title>Selected and alternative hanger response</title>
    <rect width="700" height="305" fill="#f9f8f3"/>
    <g font-family="Arial,sans-serif" font-size="13" fill="#27393c">
      <text x="68" y="20">Acceleration amplitude (m/s²)</text>
      ${grid}${ticks}
      <path d="M68 35V226H652" fill="none" stroke="#778888"/>
      <polyline points="${points(other.sweep)}" fill="none" stroke="#687670" stroke-width="2" stroke-dasharray="6 4"/>
      <polyline points="${points(result.sweep)}" fill="none" stroke="#11716b" stroke-width="2.5"/>
      <circle cx="${x(peak.frequency)}" cy="${y(peak.acceleration)}" r="4.5" fill="#a46135"/>
      <text x="360" y="267" text-anchor="middle">Forcing frequency (Hz)</text>
      <path d="M68 285h24" stroke="#11716b" stroke-width="2.5"/>
      <text x="100" y="289">Selected hanger</text>
      <path d="M240 285h24" stroke="#687670" stroke-width="2" stroke-dasharray="6 4"/>
      <text x="272" y="289">${otherStation === "50" ? "Midspan" : "One-third"} hanger · same deck depth</text>
    </g>`;
}

function selectAtriumFrequency() {
  stopAtriumAnimation();
  const { result } = atriumState;
  const peak = result.peaks[Number(atriumFrequency.value)];
  const amplitude = Math.max(...peak.real.map((real, i) => Math.hypot(real, peak.imaginary[i])));
  atriumState.peak = peak;
  atriumState.warp = Math.max(1, Math.round(220 / amplitude));
  colorLimit = Math.max(...peak.real.filter((_, i) => i % 3 === 2)
    .map((real, i) => Math.hypot(real, peak.imaginary[3 * i + 2])));
  const index = 3 * result.sample + 2;
  atriumState.phase = -Math.atan2(peak.imaginary[index], peak.real[index]);
  document.querySelector("#atrium-amplitude").textContent = format.format(peak.frequency)
    + " Hz · " + format.format(peak.acceleration) + " m/s² at walking edge · Motion scale ×" + atriumState.warp;
  drawAtriumChart(result, peak);
  showAtriumPhase(atriumState.phase);
  requestFrame();
}

function showAtriumPhase(phase) {
  const { result, peak, warp, context } = atriumState;
  const cosine = Math.cos(phase);
  const sine = Math.sin(phase);
  const points = result.points.map((value, i) =>
    value + warp * (peak.real[i] * cosine - peak.imaginary[i] * sine) / 1000);
  const base = result.hanger.map((value, axis) => value + result.attachment.reduce((sum, node) => {
    const i = 3 * node + axis;
    return sum + (points[i] - result.points[i]) / result.attachment.length;
  }, 0));
  const [x, y, z] = result.hanger;
  const vertical = peak.real.filter((_, i) => i % 3 === 2)
    .map((real, i) => real * cosine - peak.imaginary[3 * i + 2] * sine);
  const deckMotion = (node, axis) => points[3 * node + axis] - result.points[3 * node + axis];
  const movedContext = context.map(part => {
    if (part.fixed) return part;
    const moved = part.points.map((coordinate, index) => {
      const axis = index % 3;
      if (part.socket) return coordinate + base[axis] - result.hanger[axis];
      const [a, b, weight] = part.attachment[Math.floor(index / 3)];
      return coordinate + (1 - weight) * deckMotion(a, axis) + weight * deckMotion(b, axis);
    });
    return { ...part, points: moved };
  });
  parts = [{ points, faces: result.faces, vertical }, ...movedContext,
           { points: [...base, x, y, z + result.hanger_length], faces: [[0, 1]], material: "steel", diameter: .016 }];
}

atriumFrequency.addEventListener("change", selectAtriumFrequency);
atriumAnimation.addEventListener("click", () => {
  if (atriumFrame) {
    stopAtriumAnimation();
    return;
  }
  const start = performance.now();
  atriumAnimation.setAttribute("aria-pressed", "true");
  atriumAnimation.textContent = "Pause vibration";
  function animate(now) {
    showAtriumPhase(atriumState.phase + 2 * Math.PI * (now - start) / 1800);
    render();
    atriumFrame = requestAnimationFrame(animate);
  }
  atriumFrame = requestAnimationFrame(animate);
});

function setHousingRows(section, values) {
  section.querySelector("tbody").replaceChildren(...values.map(row => {
    const tr = document.createElement("tr");
    for (const [index, value] of row.entries()) {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      tr.append(cell);
    }
    return tr;
  }));
}

function showHousingOptimization(variant) {
  const { study, uniform_volume_m3: uniform, optimized_volume_m3: optimized } = variant;
  const saving = 100 * (1 - optimized / uniform);
  housingOptimization.querySelector("#housing-summary").textContent = "Uniform "
    + format.format(uniform) + " m³ · Optimised " + format.format(optimized) + " m³ · "
    + format.format(saving) + "% reduction";
  const limit = openingFormat.format(1000 * study.drift_limit) + " ‰";
  housingOptimization.querySelector("#housing-limit").textContent = limit;
  housingOptimization.querySelector("#housing-equation-limit").textContent = limit;
  housingOptimization.querySelector("#housing-bounds").textContent =
    Math.round(1000 * study.minimum_thickness_m) + "–" + Math.round(1000 * study.maximum_thickness_m) + " mm";
  const names = ["Lower band", "Middle band", "Upper band"];
  const housing = window.brutalistCases;
  const count = width.value;
  housingOptimization.querySelector("#housing-storeys").textContent = count;
  housingOptimization.querySelector("#housing-slab").textContent = Math.round(1000 * housing.slab_thickness_m);
  housingOptimization.querySelector("#housing-wind").textContent = housing.wind_pressure_pa / 1000 + " kPa";
  const initial = housing.variants[count + "-uniform"].result.thickness_m;
  const final = housing.variants[count + "-optimized"].result;
  const thicknesses = final.thickness_m.map((t, i) => Math.round(1000 * initial[i]) + " → " + Math.round(1000 * t));
  setHousingRows(housingOptimization, names.map((name, i) => {
    const first = Math.ceil(i * count / 3) + 1;
    const last = Math.ceil((i + 1) * count / 3);
    return [name, first + "–" + last, thicknesses[2 * i], thicknesses[2 * i + 1]];
  }));
  const drift = final.drifts.map(Math.abs);
  const critical = drift.indexOf(Math.max(...drift)) + 1;
  const bounded = study.continuous_peak_drift / study.drift_limit >= .99;
  housingOptimization.querySelector("#housing-governing").textContent =
    (bounded ? "Drift governs at storey " + critical : "Minimum wall thickness governs")
    + " · " + study.method + " · " + study.evaluations;
}

function showPlan() {
  const key = project.selected.join("-");
  const name = drawing === "comparison" ? drawing : key + "-" + drawing;
  const path = "plans/" + project.planFolder + "/" + name + ".svg";
  for (const button of drawingButtons) {
    button.hidden = button.dataset.drawing === "comparison" && project !== extension;
    button.setAttribute("aria-pressed", String(button.dataset.drawing === drawing));
    if (button.dataset.drawing === drawing) planSheet.alt = button.textContent + " · " + project.title;
  }
  if (planSheet.getAttribute("src") === path) return;
  planLink.hidden = true;
  planMissing.hidden = true;
  planLink.href = path;
  planSheet.src = path;
}

for (const button of drawingButtons) {
  button.addEventListener("click", () => {
    drawing = button.dataset.drawing;
    showPlan();
  });
}
planSheet.addEventListener("load", () => {
  planLink.hidden = false;
  planMissing.hidden = true;
});
planSheet.addEventListener("error", () => {
  planLink.hidden = true;
  planMissing.hidden = false;
  planSheet.removeAttribute("src");
});

function thickenGableRoof(points, reference, shellFaces, vertical, cad, slope, faces) {
  const roof = cad.find((part) => part.material === "roof");
  if (!roof) return { points, faces: shellFaces, vertical };

  const eaveX = Math.min(...roof.points.filter((_, i) => i % 3 === 0));
  const eaveZ = roof.points.filter((_, i) => i % 3 === 2 && roof.points[i - 2] === eaveX);
  const halfThickness = (Math.max(...eaveZ) - Math.min(...eaveZ)) / 2;
  if (!(halfThickness > 0)) return { points, faces: shellFaces, vertical };

  const lower = [...points];
  const upper = [...points];
  const xs = reference.filter((_, i) => i % 3 === 0);
  const ys = reference.filter((_, i) => i % 3 === 1);
  const xEnds = [Math.min(...xs), Math.max(...xs)];
  const yEnds = [Math.min(...ys), Math.max(...ys)];
  const roofNodes = new Set(shellFaces.flat());
  const columnHeads = new Set(faces.filter(face => face.length === 2).flat().filter(node => roofNodes.has(node)));
  const overhang = gable.columnSide / 2;
  for (const node of roofNodes) {
    const i = node * 3;
    const xEnd = xEnds.indexOf(reference[i]);
    const yEnd = yEnds.indexOf(reference[i + 1]);
    for (const [vertices, offset] of [[lower, -halfThickness], [upper, halfThickness]]) {
      if (xEnd >= 0) vertices[i] += xEnd === 0 ? -overhang : overhang;
      if (yEnd >= 0) vertices[i + 1] += yEnd === 0 ? -Math.max(0, overhang + yEnds[0]) : overhang;
      vertices[i + 2] += offset - (xEnd >= 0 ? overhang * slope : 0);
    }
  }
  const soffits = new Map();

  for (const face of shellFaces) {
    const corner = face.find(node => columnHeads.has(node) && !soffits.has(node));
    if (corner !== undefined) {
      const i = face.indexOf(corner);
      const [a, b, c] = [face[i], face[(i + 1) % face.length], face[(i + face.length - 1) % face.length]]
        .map((node) => lower.slice(node * 3, node * 3 + 3));
      const [bx, by, bz] = b.map((value, axis) => value - a[axis]);
      const [cx, cy, cz] = c.map((value, axis) => value - a[axis]);
      const area = bx * cy - by * cx;
      if (Math.abs(area) > 1e-9) {
        const dzdx = (bz * cy - cz * by) / area;
        const dzdy = (bx * cz - cx * bz) / area;
        soffits.set(corner, (x, y) => a[2] + dzdx * (x - a[0]) + dzdy * (y - a[1]));
      }
    }
  }

  return { ...closeShell(lower, upper, shellFaces, vertical), soffits };
}

function closeShell(lower, upper, shellFaces, vertical) {
  const count = lower.length / 3;
  const faces = [];
  const perimeter = new Map();
  for (const face of shellFaces) {
    faces.push([...face].reverse(), face.map((node) => node + count));
    for (let i = 0; i < face.length; i++) {
      const a = face[i];
      const b = face[(i + 1) % face.length];
      const key = Math.min(a, b) + ":" + Math.max(a, b);
      if (perimeter.has(key)) perimeter.delete(key);
      else perimeter.set(key, [a, b]);
    }
  }
  for (const [a, b] of perimeter.values()) {
    faces.push([a, b, b + count, a + count]);
  }

  return { points: [...lower, ...upper], faces, vertical: [...vertical, ...vertical] };
}

function deformedHousingEmblem(cad, reference, deformed) {
  const height = window.brutalistCases.storey_height_m;
  let closest = 0;
  let distance = Infinity;
  for (let i = 0; i < reference.length; i += 3) {
    const next = Math.hypot(reference[i], reference[i+1]+5, reference[i+2]-height);
    if (next < distance) {
      closest = i;
      distance = next;
    }
  }
  const translation = reference.slice(closest, closest+3).map((value, i) => deformed[closest+i]-value);
  return cad.filter(part => ["emblem", "emblemHammer", "emblemBacking"].includes(part.material))
    .map(part => ({ ...part, points: part.points.map((value, i) => value+translation[i%3]) }));
}

function hyparFrameMesh(axisPoints, edges, geometry) {
  const { tube_width_m: width, tube_depth_m: depth } = geometry;
  const points = [], faces = [];
  for (const [a, b] of edges) {
    const p = axisPoints.slice(3*a, 3*a+3);
    const q = axisPoints.slice(3*b, 3*b+3);
    const [dx, dy, dz] = q.map((value, i) => value - p[i]);
    const horizontal = Math.hypot(dx, dy);
    const length = Math.hypot(horizontal, dz);
    if (horizontal < 1e-8) continue;
    const across = [-dy/horizontal, dx/horizontal, 0];
    const up = [-dx*dz/(horizontal*length), -dy*dz/(horizontal*length), horizontal/length];
    const start = points.length / 3;
    for (const centre of [p,q]) {
      for (const [u,v] of [[-1,-1],[1,-1],[1,1],[-1,1]]) {
        points.push(...centre.map((value, i) => value + u*width/2*across[i] + v*depth/2*up[i]));
      }
    }
    for (let i = 0; i < 4; i++) {
      const j = (i+1) % 4;
      faces.push([start+i,start+j,start+4+j,start+4+i]);
    }
    faces.push([start,start+1,start+2,start+3],[start+4,start+5,start+6,start+7]);
  }
  return { points, faces, material: "hyparFrame" };
}

function housingDeformedMeshes(points, result, displacement) {
  const storeys = Number(width.value);
  const housing = window.brutalistCases;
  const reference = result.points;
  const groups = new Map();
  const matches = (indices, axis) => indices.every(i => reference[3*i+axis] === reference[3*indices[0]+axis]);
  for (const face of result.faces) {
    const axis = [2, 0, 1].find(i => matches(face, i));
    const level = reference[3*face[0]+axis];
    const z = Math.min(...face.map(i => reference[3*i+2]));
    const core = face.every(i => Math.abs(reference[3*i]) <= 2 && Math.abs(reference[3*i+1]) <= 2);
    const band = Math.min(2, Math.floor(3 * Math.floor((z+1e-7)/housing.storey_height_m) / storeys));
    const group = axis === 2 ? "slab:" + level : [axis, level, core, band].join(":");
    const t = axis === 2 ? housing.slab_thickness_m : result.thickness_m[2*band + (core ? 0 : 1)];
    if (!groups.has(group)) groups.set(group, { axis, t, faces: [] });
    groups.get(group).faces.push(face);
  }
  return [...groups.values()].map(({ axis, t, faces }) => {
    const map = new Map();
    const low = [], high = [], amplitudes = [];
    const remapped = faces.map(face => face.map(i => {
      if (!map.has(i)) {
        map.set(i, map.size);
        const p = points.slice(3*i,3*i+3);
        low.push(...p.map((value, j) => j === axis ? value-t/2 : value));
        high.push(...p.map((value, j) => j === axis ? value+t/2 : value));
        amplitudes.push(displacement[i]);
      }
      return map.get(i);
    }));
    return closeShell(low, high, remapped, amplitudes);
  });
}

function shelterDeformedMeshes(deformed, result, vertical, cad) {
  const reference = result.points;
  const roof = cad.find(part => part.material === "roof");
  const bounds = (points, axis) => {
    const values = points.filter((_, i) => i % 3 === axis);
    return [Math.min(...values), Math.max(...values)];
  };
  const [left, right] = bounds(roof.points, 0);
  const [, rear] = bounds(roof.points, 1);
  const [soffit, roofTop] = bounds(roof.points, 2);
  const [leftAxis, rightAxis] = bounds(reference, 0);
  const [, rearAxis] = bounds(reference, 1);
  const [, roofAxis] = bounds(reference, 2);
  const wallHalf = leftAxis - left;
  const roofHalf = (roofTop - soffit) / 2;
  const near = (a, b) => Math.abs(a - b) < 1e-5;
  const surfaces = { roof: [], rear: [], left: [], right: [] };
  for (const face of result.faces) {
    if (face.every(node => near(reference[3 * node + 2], roofAxis))) surfaces.roof.push(face);
    else if (face.every(node => near(reference[3 * node + 1], rearAxis))) surfaces.rear.push(face);
    else if (near(reference[3 * face[0]], leftAxis)) surfaces.left.push(face);
    else surfaces.right.push(face);
  }

  return Object.entries(surfaces).map(([name, faces]) => {
    const lower = [...deformed], upper = [...deformed];
    for (const node of new Set(faces.flat())) {
      const i = 3 * node;
      const [x, y, z] = reference.slice(i, i + 3);
      for (const [points, side] of [[lower, -1], [upper, 1]]) {
        if (name === "roof" || name === "rear") {
          if (near(x, leftAxis)) points[i] += left - leftAxis;
          if (near(x, rightAxis)) points[i] += right - rightAxis;
        }
        if (name === "roof") {
          if (near(y, rearAxis)) points[i + 1] += rear - rearAxis;
          points[i + 2] += side * roofHalf;
        } else {
          if (name === "rear") points[i + 1] += side * wallHalf;
          else {
            points[i] += side * wallHalf;
            if (near(y, rearAxis)) points[i + 1] -= wallHalf;
          }
          if (near(z, roofAxis)) points[i + 2] -= roofHalf;
        }
      }
    }
    return closeShell(lower, upper, faces, vertical);
  });
}

function extensionDetailLimit() {
  return Math.ceil(Math.max(...Object.values(extensionDetails.cases).map(result => result.compression_mpa)) / 10) * 10;
}

function showExtensionDetail(result) {
  const { geometry, connection } = extensionDetails;
  const flange = geometry.flange_thickness_m / 2;
  const plate = connection.bearing_plate_thickness_m;
  const stiffener = connection.stiffener_thickness_m / 2;
  const { points, faces } = result;

  function solid(group, axis, low, high) {
    const offset = distance => points.map((value, i) => i % 3 === axis ? value + distance : value);
    return { ...closeShell(offset(low), offset(high), group, []), vertical: undefined, material: "steel" };
  }

  parts = [{ points, faces: faces.web, material: "steel", compression: result.stress_mpa },
           solid(faces.flanges, 2, -flange, flange),
           solid(faces.plate, 2, -flange, flange + plate)];
  if (faces.stiffeners.length) parts.push(solid(faces.stiffeners, 0, -stiffener, stiffener));
  document.querySelector("#connection-scale").textContent =
    "Vertical web compression · 0 to " + extensionDetailLimit() + " MPa · Undeformed geometry";
  readout.textContent = "Peak element-centre web compression " + format.format(result.compression_mpa)
    + " MPa · Flange-to-flange shortening at column " + openingFormat.format(result.shortening_mm) + " mm";
  document.querySelector("#connection-assumptions").textContent =
    geometry.column_offset_m.toFixed(2) + " m column offset · " + geometry.beam_depth_m * 1000 + " mm beam · "
    + extensionDetails.column_force_kn + " kN column load · " + plate * 1000 + " mm bonded bearing plate"
    + (faces.stiffeners.length ? " · " + 2 * stiffener * 1000 + " mm paired stiffeners" : "");
}

function extensionDeformedMeshes(points, result, vertical, variant) {
  const { web_thickness_m: web, flange_thickness_m: flange } = variant.geometry;
  const flanges = [];
  const webFaces = [];
  for (const face of result.faces) {
    const level = result.points[3 * face[0] + 2];
    (face.every(node => result.points[3 * node + 2] === level) ? flanges : webFaces).push(face);
  }
  function solid(faces, axis, half) {
    const bottom = points.map((value, i) => i % 3 === axis ? value - half : value);
    const top = points.map((value, i) => i % 3 === axis ? value + half : value);
    return closeShell(bottom, top, faces, vertical);
  }
  const seatDrop = result.seat_mm * extension.warp / 1000;
  const walls = variant.cad.filter(part => part.material === "wall");
  const upperFloors = variant.cad.filter(part => part.material === "timber").map(part => ({
    ...part,
    points: part.points.map((value, i) => i % 3 === 2 ? value - seatDrop : value),
  }));
  return [...walls, ...upperFloors, solid(flanges, 2, flange/2), solid(webFaces, 1, web/2)];
}

function bridgeDeformedMeshes(points, result, vertical, geometry) {
  const { span_m: span, deck_width_m: width, deck_thickness_m: deck,
          arch_width_m: arch, abutment_thickness_m: abutment } = geometry;
  const shells = result.faces.filter(face => face.length === 4);
  const sameCoordinate = (face, axis, value) => face.every(node => Math.abs(result.points[node * 3 + axis] - value) < 1e-5);
  function solid(faces, axis, low, high, outline = points) {
    const base = outline.map((value, i) => i % 3 === axis ? value + low : value);
    const top = outline.map((value, i) => i % 3 === axis ? value + high : value);
    return closeShell(base, top, faces, vertical);
  }
  const deckOutline = points.map((value, i) => {
    const reference = result.points[i];
    return i % 3 === 1 && Math.abs(Math.abs(reference) - width / 2) < 1e-5
      ? value + Math.sign(reference) * arch / 2 : value;
  });
  const edges = result.faces.filter(face => face.length === 2);
  const parts = [solid(shells.filter(face => sameCoordinate(face, 2, 0)), 2, -deck/2, deck/2, deckOutline),
                 { points, faces: edges, vertical, diameter: Number(thickness.value) / 1000,
                   hangerChanges: result.hanger_changes_kn }];
  for (const sign of [-1, 1]) {
    parts.push(solid(shells.filter(face => sameCoordinate(face, 1, sign * width / 2)), 1, -arch/2, arch/2));
  }
  parts.push(solid(shells.filter(face => sameCoordinate(face, 0, 0)), 0, -abutment, 0, deckOutline),
             solid(shells.filter(face => sameCoordinate(face, 0, span)), 0, 0, abutment, deckOutline));
  if (result.hanger_changes_kn) {
    const anchor = [span / 2, -width / 2, 0];
    const index = result.points.findIndex((_, i) => i % 3 === 0
      && anchor.every((value, axis) => Math.abs(result.points[i + axis] - value) < 1e-5));
    if (index >= 0) {
      const [x, y, z] = points.slice(index, index + 3);
      const marker = { points: [], faces: [], color: [120, 54, 149] };
      const segments = 20;
      for (let i = 0; i < segments; i++) {
        const angle = 2 * Math.PI * i / segments;
        marker.points.push(x + .16 * Math.cos(angle), y + .16 * Math.sin(angle), z + deck / 2 + .015);
        marker.faces.push([i, (i + 1) % segments]);
      }
      parts.push(marker);
    }
  }
  return parts;
}

function houseDeformedMeshes(deformed, result, vertical, cad) {
  const boxes = cad.filter((part) => part.material === "wall").map(({ points }) =>
    [0, 1, 2].map((axis) => {
      const values = points.filter((_, i) => i % 3 === axis);
      return [Math.min(...values), Math.max(...values)];
    }));
  const size = ([min, max]) => max - min;
  const slabs = boxes.filter(([x, y, z]) => size(z) < Math.min(size(x), size(y)))
    .sort((a, b) => a[2][0] - b[2][0]);
  const walls = boxes.filter(([x, y, z]) => size(z) > Math.max(Math.min(size(x), size(y)), 1)
    && Math.max(size(x), size(y)) > size(z));
  const column = boxes.find(([x, y, z]) => size(z) > Math.max(size(x), size(y)));
  if (!slabs.length || !walls.length || !column) {
    return [{ points: deformed, faces: result.faces, vertical }];
  }

  const reference = result.points;
  const wallHalf = Math.min(...walls.map(([x, y]) => Math.min(size(x), size(y)))) / 2;
  const roof = slabs.at(-1);
  const roofLevel = (roof[2][0] + roof[2][1]) / 2;
  const roofHalf = size(roof[2]) / 2;
  const groups = new Map();
  const beamFaces = [];
  const soffits = new Map();

  for (const face of result.faces) {
    if (face.length === 2) {
      beamFaces.push(face);
      for (const node of face) {
        if (Math.abs(reference[node * 3 + 2] - roofLevel) < 1e-5) {
          soffits.set(node, () => deformed[node * 3 + 2] - roofHalf);
        }
      }
      continue;
    }
    const axis = [2, 0, 1].find((axis) =>
      face.every((node) => Math.abs(reference[3 * node + axis] - reference[3 * face[0] + axis]) < 1e-6));
    const level = reference[3 * face[0] + axis];
    const key = axis + ":" + level;
    if (!groups.has(key)) groups.set(key, { axis, level, faces: [] });
    groups.get(key).faces.push(face);
  }

  const parts = [];
  for (const { axis, level, faces } of groups.values()) {
    const lower = [...deformed];
    const upper = [...deformed];
    const nodes = new Set(faces.flat());
    const slab = slabs.find((box) => Math.abs((box[2][0] + box[2][1]) / 2 - level) < 1e-5);
    const half = axis === 2 && slab ? size(slab[2]) / 2 : wallHalf;
    for (const node of nodes) {
      const i = node * 3;
      for (const [points, sign] of [[lower, -1], [upper, 1]]) {
        points[i + axis] += sign * half;
        if (axis === 2) {
          for (const direction of [0, 1]) {
            if (Math.abs(reference[i + direction] - wallHalf) < 1e-5) points[i + direction] -= wallHalf;
          }
        } else {
          const along = 1 - axis;
          if (Math.abs(reference[i + along] - wallHalf) < 1e-5) {
            points[i + along] += axis === 0 ? wallHalf : -wallHalf;
          }
          if (Math.abs(reference[i + 2] - roofLevel) < 1e-5) points[i + 2] -= roofHalf;
        }
      }
    }
    parts.push(closeShell(lower, upper, faces, vertical));
  }
  parts.push(squareColumnMesh(deformed, beamFaces, vertical, size(column[0]), soffits));
  return parts;
}

function squareColumnMesh(axisPoints, elements, axisDisplacement, side, soffits) {
  const points = [];
  const faces = [];
  const vertical = [];
  const sections = new Map();
  const connections = new Map();
  const half = side / 2;

  function section(node) {
    if (!sections.has(node)) {
      const [x, y, z] = axisPoints.slice(node * 3, node * 3 + 3);
      sections.set(node, points.length / 3);
      for (const [dx, dy] of [[-half, -half], [half, -half], [half, half], [-half, half]]) {
        const soffit = soffits?.get(node);
        points.push(x + dx, y + dy, soffit ? soffit(x + dx, y + dy) : z);
        vertical.push(axisDisplacement[node]);
      }
    }
    connections.set(node, (connections.get(node) ?? 0) + 1);
    return sections.get(node);
  }

  for (const element of elements) {
    if (element.length !== 2) continue;
    const a = section(element[0]);
    const b = section(element[1]);
    for (let i = 0; i < 4; i++) {
      const j = (i + 1) % 4;
      faces.push([a + i, a + j, b + j, b + i]);
    }
  }
  for (const [node, start] of sections) {
    if (connections.get(node) === 1) faces.push([start, start + 1, start + 2, start + 3]);
  }
  return { points, faces, vertical };
}

function houseCadMesh(cad) {
  if (houseRenderMeshes.has(cad)) return houseRenderMeshes.get(cad);
  const meshes = cad.map(({ points: source, faces, material }) => {
    const points = [...source];
    const refined = [];
    const pending = [...faces];
    const midpoints = new Map();
    while (pending.length) {
      const triangle = pending.pop();
      const lengths = triangle.map((a, i) => {
        const b = triangle[(i + 1) % 3];
        return Math.hypot(...[0, 1, 2].map((axis) => points[a * 3 + axis] - points[b * 3 + axis]));
      });
      const longest = Math.max(...lengths);
      if (renderDepth || longest <= 0.85) {
        refined.push(triangle);
        continue;
      }
      const i = lengths.indexOf(longest);
      const [a, b, c] = [0, 1, 2].map((offset) => triangle[(i + offset) % 3]);
      const key = Math.min(a, b) + ":" + Math.max(a, b);
      if (!midpoints.has(key)) {
        midpoints.set(key, points.length / 3);
        for (let axis = 0; axis < 3; axis++) points.push((points[a * 3 + axis] + points[b * 3 + axis]) / 2);
      }
      const mid = midpoints.get(key);
      pending.push([a, mid, c], [mid, b, c]);
    }
    const isColumn = material === "wall" && [0, 1].every((axis) => {
      const coords = source.filter((_, i) => i % 3 === axis);
      return Math.max(...coords) - Math.min(...coords) < 0.5;
    });
    return { points, faces: refined, material: isColumn ? "column" : material };
  });
  houseRenderMeshes.set(cad, meshes);
  return meshes;
}

function resetCamera() {
  camera = {
    ...initialCamera,
    azimuth: project.azimuth ?? initialCamera.azimuth,
    elevation: project.elevation ?? initialCamera.elevation,
  };
}

function showObservatory(result) {
  const deformed = mode === "result";
  const points = deformed
    ? result.points.map((value, i) => value + result.displacement[i] * project.warp / 1000)
    : result.points;
  const vertical = deformed ? result.displacement.filter((_, i) => i % 3 === 2) : undefined;
  parts = deformed
    ? [{ points, faces: result.shell, material: "wall" }]
    : [...sweep.geometry];
  parts.push(
    { points, faces: result.ribs, material: "steel", vertical, diameter: Number(thickness.value) / 1000 },
    { points, faces: result.ring, material: "steel", vertical, diameter: 0.12 },
  );

  const gap = Math.abs(result.gap_mm);
  const movement = gap < 0.005 ? "maximum slit width change"
    : result.gap_mm < 0 ? "maximum slit closure" : "maximum slit opening";
  readout.textContent = format.format(gap) + " mm " + movement
    + " · " + format.format(result.front_mm) + " mm maximum downward displacement";
}

function canopySubtitle(angle) {
  return angle === undefined ? "Local FE model of the anchorage" : "Tie rod at " + angle + "° · Local FE model of the anchorage";
}

function showCanopy(variant) {
  const result = variant.result;
  const deformed = mode === "result";
  boltForces.hidden = !deformed;
  const places = result.bolts.length === 6
    ? ["Top", "Middle", "Bottom"] : ["Top", "Bottom"];
  const cells = result.bolts.map((bolt, i) => {
    const row = document.createElement("tr");
    const side = i % 2 === 0 ? "left" : "right";
    for (const value of [places[Math.floor(i / 2)] + " " + side,
                         format.format(bolt.axial_kn), format.format(bolt.shear_kn)]) {
      row.insertCell().textContent = value;
    }
    return row;
  });
  boltForces.tBodies[0].replaceChildren(...cells);

  if (deformed) {
    const points = result.points.map((value, i) => value + result.displacement[i] * project.warp / 1000);
    const colorValues = points.filter((_, i) => i % 3 === 0).map((_, i) => {
      const j = i * 3;
      return -Math.hypot(result.displacement[j], result.displacement[j+1], result.displacement[j+2]);
    });
    parts = Object.entries(result.surfaces).map(([body, faces]) => body === "1"
      ? { points, faces, material: "wall", opacity: 0.25 }
      : { points, faces, vertical: colorValues });
  } else {
    parts = houseCadMesh(variant.cad);
  }
  const peak = Math.max(...result.bolts.map((bolt) => bolt.axial_kn));
  readout.textContent = "Plate opening " + openingFormat.format(result.opening_mm)
    + " mm · Maximum bolt tension " + format.format(peak) + " kN";
}

function requestFrame() {
  if (framePending) return;
  framePending = true;
  requestAnimationFrame(() => {
    framePending = false;
    render();
  });
}

function displacementColor(millimetres) {
  if (project === house || project.signed) {
    const neutral = [225, 231, 223];
    const end = millimetres < 0 ? [61, 114, 154] : [203, 126, 73];
    const ratio = Math.min(1, Math.abs(millimetres) / colorLimit);
    return neutral.map((value, i) => value + ratio * (end[i] - value));
  }
  const steps = Math.min(2, 2 * Math.max(0, millimetres) / colorLimit);
  const index = Math.min(1, Math.floor(steps));
  const fraction = steps - index;
  return colorRamp[index].map((value, channel) =>
    value + fraction * (colorRamp[index + 1][channel] - value));
}

function smoothSlabCut(part) {
  if (!part.compression) return part;
  const samples = new Map();
  const keys = part.faces.map((face, index) => {
    const x = part.points[3 * face[0]];
    const axis = face.every(node => part.points[3 * node] === x) ? 0 : 1;
    const plane = part.points[3 * face[0] + axis];
    return face.map(node => {
      const key = [axis, plane, node].join(":");
      const [sum, count] = samples.get(key) ?? [0, 0];
      samples.set(key, [sum + part.compression[index], count + 1]);
      return key;
    });
  });
  return { ...part, cornerStress: keys.map(face => face.map(key => {
    const [sum, count] = samples.get(key);
    return sum / count;
  })) };
}

function compressionColor(fraction) {
  const clamped = Math.max(0, Math.min(1, fraction));
  const [low, high] = [[231, 235, 228], [176, 57, 30]];
  return low.map((value, i) => value + (high[i] - value) * clamped);
}

function hangerChangeColor(change) {
  const fraction = Math.min(1, Math.abs(change) / hangerChangeLimit);
  const neutral = [130, 138, 127];
  const extreme = change < 0 ? [35, 109, 193] : [226, 73, 42];
  return neutral.map((value, i) => value + fraction * (extreme[i] - value));
}

function render() {
  const { clientWidth: w, clientHeight: h } = canvas;
  if (!w || !h) return;
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(w * pixelRatio);
  const pixelHeight = Math.round(h * pixelRatio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, w, h);

  const { azimuth, elevation, zoom } = camera;
  const ca = Math.cos(azimuth), sa = Math.sin(azimuth);
  const ce = Math.cos(elevation), se = Math.sin(elevation);
  const detail = project === canopy && mode === "result";
  const slabGeometry = project === slab && mode === "cad";
  const connection = project === extension && mode === "result" && extensionDetails?.cases[extensionStudy.value];
  const compressionLimit = connection ? extensionDetailLimit() : project === slab ? .5 : 1;
  const span = detail ? 0.68 : (project.span ?? Number(width.value));
  const scale = project === brutalist ? Math.min(w / 27, h / (window.brutalistCases.storey_height_m * Number(width.value) + 5)) * zoom
    : connection ? Math.min(w / 1.50, h / 0.85) * zoom
    : detail ? Math.min(w / 1.05, h / 0.73) * zoom
    : slabGeometry ? Math.min(w / 6.5, h / 4.3) * zoom
    : Math.min(w / (span + 3.5), h / project.viewHeight) * zoom;
  const midX = connection ? extensionDetails.geometry.column_offset_m
    : slabGeometry ? .55
    : project === hypar ? Number(thickness.value) / 2 - .25 : project.centerX ?? (project.span ? 0 : span / 2);
  const [midY, midZ] = connection ? [0, extensionDetails.geometry.beam_depth_m / 2]
    : detail ? [-0.09, -0.1]
    : slabGeometry ? [0, -.85]
    : project === brutalist ? [0, window.brutalistCases.storey_height_m * Number(width.value) / 2]
    : project === gable ? [project.center[0] - Number(thirdParameter.value) / 2, project.center[1]] : project.center;
  const polygons = [];

  for (const { points, faces, material, vertical, diameter, opacity, compression, cornerStress, hangerChanges, color } of parts) {
    const projected = [];
    for (let i = 0; i < points.length; i += 3) {
      const x = points[i] - midX, y = points[i + 1] - midY, z = points[i + 2] - midZ;
      projected.push([
        w / 2 + scale * (ca * x + sa * y),
        h / 2 - scale * (-se * sa * x + se * ca * y + ce * z),
        ce * (sa * x - ca * y) + se * z,
      ]);
    }
    for (const [faceIndex, face] of faces.entries()) {
      const corners = face.map((i) => projected[i]);
      const depth = corners.reduce((sum, point) => sum + point[2], 0) / corners.length;
      const averageDrop = vertical ? -face.reduce((sum, i) => sum + vertical[i], 0) / face.length : 0;
      const base = hangerChanges
        ? hangerChangeColor(hangerChanges[faceIndex])
        : compression
        ? compressionColor(compression[faceIndex] / compressionLimit)
        : vertical ? displacementColor(averageDrop) : color ?? solidColors[material];
      if (face.length === 2) {
        polygons.push({ corners, depth, lineWidth: diameter ? Math.max(hangerChanges ? 3 : 1.2, scale * diameter) : 3, color: base.map((value) => Math.round(value * 0.76)) });
        continue;
      }
      const [a, b, c] = face.map((i) => i * 3);
      const ab = [points[b] - points[a], points[b + 1] - points[a + 1], points[b + 2] - points[a + 2]];
      const ac = [points[c] - points[a], points[c + 1] - points[a + 1], points[c + 2] - points[a + 2]];
      const normal = [ab[1] * ac[2] - ab[2] * ac[1],
                      ab[2] * ac[0] - ab[0] * ac[2],
                      ab[0] * ac[1] - ab[1] * ac[0]];
      const length = Math.hypot(...normal);
      if (length < 1e-12) continue;
      const light = Math.abs((0.35 * normal[0] - 0.32 * normal[1] + 0.88 * normal[2]) / length);
      const shade = 0.69 + 0.33 * light;
      polygons.push({
        corners,
        depth,
        opacity: opacity ?? (material === "glass" && (project === observatory || project === house || project === canopy) ? 0.19
          : material === "door" ? 0.42 : 1),
        color: base.map((value) => Math.round(value * shade)),
        cornerColors: cornerStress?.[faceIndex].map(value =>
          compressionColor(value / compressionLimit).map(channel => channel * shade)),
      });
    }
  }

  polygons.sort((a, b) => a.depth - b.depth);
  if ((mode === "cad" || project === shelter || project === gable || project === house || project === hypar || project === bridge || project === extension || project === brutalist || project === terrace || project === atrium || project === cabin || project === facade || project === auditorium || project === vierendeel || project === slab) && renderDepth?.(polygons, context, w, h)) return;

  for (const { corners, color, opacity = 1, lineWidth } of polygons) {
    const paint = "rgb(" + color.join(",") + ")";
    context.beginPath();
    corners.forEach(([x, y], i) => i ? context.lineTo(x, y) : context.moveTo(x, y));
    if (corners.length > 2) {
      context.closePath();
      context.fillStyle = paint;
      context.globalAlpha = opacity;
      context.fill();
      context.globalAlpha = 1;
      if (opacity < 1) continue;
    }
    context.strokeStyle = paint;
    context.lineWidth = lineWidth ?? 0.65;
    context.lineCap = lineWidth ? "round" : "butt";
    context.stroke();
  }
}

function rotate(dx, dy) {
  camera.azimuth += dx;
  camera.elevation = Math.max(-1.48, Math.min(1.48, camera.elevation + dy));
  requestFrame();
}

function zoomBy(amount) {
  camera.zoom = Math.max(0.45, Math.min(4, camera.zoom * amount));
  requestFrame();
}

hyparLoad.addEventListener("change", selectVariant);
gableLoad.addEventListener("change", selectVariant);
bridgeCondition.addEventListener("change", selectVariant);
extensionStudy.addEventListener("change", () => {
  resetCamera();
  selectVariant();
});
for (const select of parameterSelects) select.addEventListener("change", selectVariant);
for (const tab of tabs) tab.addEventListener("click", () => {
  mode = tab.id;
  selectVariant();
});
new ResizeObserver(requestFrame).observe(canvas);
canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || pointer) return;
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener("pointermove", (event) => {
  if (pointer?.id !== event.pointerId) return;
  rotate((event.clientX - pointer.x) * 0.009, (event.clientY - pointer.y) * 0.009);
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
});
canvas.addEventListener("lostpointercapture", () => { pointer = null; });
canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  zoomBy(Math.exp(-Math.sign(event.deltaY) * 0.13));
}, { passive: false });
canvas.addEventListener("keydown", (event) => {
  const directions = { ArrowLeft: [-0.12, 0], ArrowRight: [0.12, 0],
                       ArrowUp: [0, 0.12], ArrowDown: [0, -0.12] };
  if (directions[event.key]) rotate(...directions[event.key]);
  else if (event.key === "+" || event.key === "=") zoomBy(1.15);
  else if (event.key === "-") zoomBy(1 / 1.15);
  else return;
  event.preventDefault();
});
document.querySelector("#zoom-in").addEventListener("click", () => zoomBy(1.2));
document.querySelector("#zoom-out").addEventListener("click", () => zoomBy(1 / 1.2));
document.querySelector("#reset").addEventListener("click", () => {
  resetCamera();
  requestFrame();
});

window.addEventListener("hashchange", selectProject);
selectProject();
