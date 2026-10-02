-- Fixture do "sem buracos": cada legenda termina onde a PROXIMA comeca.
--
-- E' o que o `giautosubs.py --no-gaps` grava, e o que derrubou o Resolve em
-- 27/09/2026: `endFrame` e' INCLUSIVO, entao um clipe com `recordFrame = f0` e
-- `endFrame = f1 - f0` ocupa f0..f1 - e a proxima legenda pedia o frame f1 na
-- MESMA track. Dois clipes no mesmo frame de uma track de video derrubam o
-- programa; enquanto as legendas tinham buraco entre elas, isso nunca esbarrou
-- em nada e atravessou 29 versoes do macro.
--
-- Escrito a mao e pequeno de proposito: o que o teste olha nao e' o estilo, e' o
-- `recordFrame`/`endFrame` que cada clipe pede. A 60 fps (o que o Resolve falso
-- devolve), 0.0 -> 1.0 -> 2.5 -> 4.0 da' frames 0, 60, 150 e 240 colados.
return {
  versao = 2,
  macro_versao = 4,
  estilo = "amostra_sem_buracos",
  inputs = {
    Font = "Open Sans",
    Style = "Bold",
    Size = 0.09,
    Center = { 0.5, 0.22 },
    Enabled1 = 1, Red1 = 1.0, Green1 = 1.0, Blue1 = 1.0,
    Enabled2 = 1, Red2 = 0.0, Green2 = 0.0, Blue2 = 0.0,
    Softness2 = 1, Thickness2 = 0.15,
    Enabled3 = 0,
    Enabled4 = 0,
    Enabled5 = 0,
    -- a caixa do texto, que e' o que a largura fixa mexe
    Enabled6 = 1, Red6 = 0.0, Green6 = 0.0, Blue6 = 0.0,
    Opacity6 = 0.45, Level6 = 1, _borda6 = true,
    ExtendHorizontal6 = 0.2, ExtendVertical6 = 0.12, Round6 = 0.25,
    Enabled7 = 0,
  },
  controles = {
    TextBoxEnabled = 1,
    TextBoxFixed = 1,
    TextBoxColorRed = 0.0, TextBoxColorGreen = 0.0, TextBoxColorBlue = 0.0,
    TextBoxOpacity = 0.45, TextBoxLevel = 1,
    TextBoxExtendHorizontal = 0.2, TextBoxExtendVertical = 0.12,
    TextBoxRound = 0.25,
    MetaCharsPerBox = 19, MetaLines = 1, MetaCharWidth = 0.5,
  },
  -- sem destaque: o que este fixture exercita e' a aritmetica de frames
  destaque = nil,
  speakers = {},
  track_unica = true,
  meta = {
    captions_file = [[Z:\fixture\amostra_sem_buracos.lua]],
    cut_folder = [[Z:\fixture]],
    transcript = [[Z:\fixture\amostra.giautosubs.json]],
    style = "amostra_sem_buracos",
    styles_file = [[Z:\fixture\estilos.json]],
    chars_per_box = 19,
    lines = 1,
    fixed_box = true,
    no_gaps = true,
  },
  segments = {
    {
      start = 0.0,
      ["end"] = 1.0,
      text = "primeira",
      speaker_id = 0,
    },
    {
      start = 1.0,
      ["end"] = 2.5,
      text = "segunda",
      speaker_id = 0,
    },
    {
      start = 2.5,
      ["end"] = 4.0,
      text = "terceira",
      speaker_id = 0,
    },
  },
}
