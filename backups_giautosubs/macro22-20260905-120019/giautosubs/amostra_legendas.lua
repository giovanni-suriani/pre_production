-- Fixture dos testes: um legendas.lua minimo, escrito a mao.
--
-- Existe porque a transcricao real do projeto ainda nao tem tempo por palavra,
-- e sem isso o caminho do destaque (o mais delicado do script: keyframe por
-- palavra no spline de character-level styling) nunca era exercitado. Aqui ele
-- e' - com caixa, sombra da caixa e dois falantes.
--
-- Formato identico ao que o giautosubs.py gera. Se ele mudar, este arquivo
-- muda junto - e' de proposito que o teste quebre nesse caso.
return {
  versao = 2,
  macro_versao = 4,
  estilo = "amostra_com_words",
  inputs = {
    Font = "Open Sans",
    Style = "Bold",
    Size = 0.09,
    Center = { 0.5, 0.22 },

    Enabled1 = 1, Red1 = 1.0, Green1 = 1.0, Blue1 = 1.0,
    Enabled2 = 1, Red2 = 0.0, Green2 = 0.0, Blue2 = 0.0,
    Softness2 = 1, Thickness2 = 0.15,
    Enabled3 = 1, Red3 = 0.0, Green3 = 0.0, Blue3 = 0.0,
    Opacity3 = 0.6, Softness3 = 1.5, _offset3 = { 0.004, -0.006 },

    -- bolha da palavra falada + sombra dela
    Enabled4 = 1, Red4 = 1.0, Green4 = 0.847059, Blue4 = 0.301961,
    Opacity4 = 1, Level4 = 2, _borda4 = true,
    ExtendHorizontal4 = 0.15, ExtendVertical4 = 0.1, Round4 = 0.4,

    Enabled5 = 1, Red5 = 0.0, Green5 = 0.0, Blue5 = 0.0,
    Opacity5 = 0.55, Softness5 = 2, Level5 = 2, _borda5 = true,
    ExtendHorizontal5 = 0.15, ExtendVertical5 = 0.1, Round5 = 0.4,
    _offset5 = { 0.005, -0.007 },

    Enabled6 = 0,
    Enabled7 = 0,
  },
  controles = {
    BubbleEnabled = 1,
    BubbleColorRed = 1.0, BubbleColorGreen = 0.847059, BubbleColorBlue = 0.301961,
    BoxShadowOnHighlight = 1,
    OutlineColorRed = 0.0, OutlineColorGreen = 0.0, OutlineColorBlue = 0.0,
  },
  destaque = {
    camadas = {
      {
        elemento = 4,
        cor_ativa = { 1.0, 0.847059, 0.301961 },
        cor_base = { 1.0, 0.847059, 0.301961 },
        on_ativo = 1, on_base = 0,
      },
      {
        elemento = 5,
        cor_ativa = { 0.0, 0.0, 0.0 },
        cor_base = { 0.0, 0.0, 0.0 },
        on_ativo = 1, on_base = 0,
      },
    },
  },
  speakers = {
    { nome = "Cupertino", cor = { 1.0, 0.847059, 0.301961 }, aplicar_em = "fill", track = 1 },
    { nome = "Heitor", cor = { 0.301961, 0.882353, 1.0 }, aplicar_em = "fill", track = 2 },
  },
  segments = {
    {
      start = 0.0,
      ["end"] = 2.0,
      text = "voce comeca ai",
      speaker_id = 1,
      words = {
        { word = "voce", start = 0.0, ["end"] = 0.4 },
        { word = " comeca", start = 0.4, ["end"] = 1.2 },
        { word = " ai", start = 1.2, ["end"] = 2.0 },
      },
    },
    {
      start = 2.0,
      ["end"] = 3.5,
      text = "nao, ja sei",
      speaker_id = 2,
      words = {
        { word = "nao,", start = 2.0, ["end"] = 2.5 },
        { word = " ja", start = 2.5, ["end"] = 2.9 },
        { word = " sei", start = 2.9, ["end"] = 3.5 },
      },
    },
    {
      -- de proposito sem `words`: e' o caso "SEM DESTAQUE" do resumo
      start = 3.5,
      ["end"] = 5.0,
      text = "sem tempo por palavra",
      speaker_id = 0,
    },
  },
}
