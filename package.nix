# SearXNG with extra colour themes (see themes.css for how they work), plus
# our own plugins: instant answers + personal site ranking (./plugins, with
# their template/CSS/JS alongside). The plugins are enabled in selfhosted.nix.
#
# The "simple" theme hard-codes its style list in four places; each is patched
# with substituteInPlace --replace-fail, so an upstream change breaks the BUILD
# loudly (nixos-rebuild fails, the running instance is untouched) instead of
# silently shipping a half-applied patch. If that happens after a
# `nix flake update nixpkgs-unstable`, re-check the four strings below.
{ searxng, lib }:

let
  # style name -> built-in base it layers on ("dark" or "light")
  styles = {
    mocha = "dark";
    tokyonight = "dark";
    gruvbox = "dark";
    nord = "dark";
    dracula = "dark";
    rosepine = "dark";
    sakura = "dark";
    latte = "light";
    bubblegum = "light";
    solarized = "light";
  };
  names = builtins.attrNames styles;
  pyList = lib.concatMapStrings (n: ", '${n}'") names;          # , 'mocha', 'nord' …
  pyListDq = lib.concatMapStrings (n: ", \"${n}\"") names;      # , "mocha", "nord" …
  jinjaMap = "{" + lib.concatStringsSep ", " (lib.mapAttrsToList (n: b: "'${n}': '${b}'") styles) + "}";
in
# toPythonModule again: overridePythonAttrs returns the bare application, whose
# requiredPythonModules would not include the added dependency (uWSGI builds its
# python env from that list).
searxng.pythonModule.pkgs.toPythonModule (searxng.overridePythonAttrs (old: {
  # segno: pure-Python QR encoder for the "qr …" instant answer
  dependencies = (old.dependencies or [ ]) ++ [ searxng.pythonModule.pkgs.segno ];

  postInstall = (old.postInstall or "") + ''
    sx=$out/${searxng.pythonModule.sitePackages}/searx

    substituteInPlace $sx/settings_defaults.py \
      --replace-fail "SIMPLE_STYLE = ('auto', 'light', 'dark', 'black')" \
                     "SIMPLE_STYLE = ('auto', 'light', 'dark', 'black'${pyList})"

    substituteInPlace $sx/preferences.py \
      --replace-fail 'choices=["", "auto", "light", "dark", "black"],' \
                     'choices=["", "auto", "light", "dark", "black"${pyListDq}],'

    substituteInPlace $sx/templates/simple/preferences/theme.html \
      --replace-fail "{%- for name in ['auto', 'light', 'dark', 'black'] -%}" \
                     "{%- for name in ['auto', 'light', 'dark', 'black'${pyList}] -%}"

    # <html class="theme-dark theme-custom theme-nord …"> for custom styles, so the
    # built-in base still applies and themes.css only repaints the variables.
    substituteInPlace $sx/templates/simple/base.html \
      --replace-fail "<html class=\"no-js theme-{{ preferences.get_value('simple_style') or 'auto' }} " \
                     "{%- set sx_style = preferences.get_value('simple_style') or 'auto' -%}{%- set sx_base = ${jinjaMap}.get(sx_style) -%}<html class=\"no-js {% if sx_base %}theme-{{ sx_base }} theme-custom {% endif %}theme-{{ sx_style }} " \
      --replace-fail "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sxng-ltr.min.css') }}\" type=\"text/css\" media=\"screen\">" \
                     "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sxng-ltr.min.css') }}\" type=\"text/css\" media=\"screen\"><link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sxng-themes.css') }}\" type=\"text/css\" media=\"screen\"><link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sxng-extras.css') }}\" type=\"text/css\" media=\"screen\"><script defer src=\"{{ url_for('static', filename='sxng-extras.js') }}\"></script>"

    cp ${./themes.css} $sx/static/themes/simple/sxng-themes.css
    cp ${./sxng-extras.css} $sx/static/themes/simple/sxng-extras.css
    cp ${./sxng-extras.js} $sx/static/themes/simple/sxng-extras.js
    cp ${./templates/answer/instant.html} $sx/templates/simple/answer/instant.html
    cp ${./plugins/smallapp_answers.py} $sx/plugins/smallapp_answers.py
    cp ${./plugins/smallapp_sites.py} $sx/plugins/smallapp_sites.py
  '';
}))
