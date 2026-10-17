-- la.lua: pandoc Lua filter for the Linear Algebra site pipeline.
-- Runs on LaTeX fragments (one box body or one stretch of running text) and makes the
-- Markdown that comes out safe for Python-Markdown + pymdownx.arithmatex:
--   * unwraps every Div (center, ...), marks the end of a proof,
--   * puts each display equation in a paragraph of its own,
--   * turns description lists into bold-run-in paragraphs,
--   * turns ordered lists that Python-Markdown cannot number ((a), (1), i., ...) into
--     paragraphs with the label written out, keeping plain "1." lists as real lists.

local function roman(n, upper)
  local vals = {{1000,'m'},{900,'cm'},{500,'d'},{400,'cd'},{100,'c'},{90,'xc'},
                {50,'l'},{40,'xl'},{10,'x'},{9,'ix'},{5,'v'},{4,'iv'},{1,'i'}}
  local out = ''
  for _, p in ipairs(vals) do
    while n >= p[1] do out = out .. p[2]; n = n - p[1] end
  end
  if upper then out = out:upper() end
  return out
end

local function label_for(n, style, delim)
  local core
  if style == 'LowerAlpha' then core = string.char(96 + ((n - 1) % 26) + 1)
  elseif style == 'UpperAlpha' then core = string.char(64 + ((n - 1) % 26) + 1)
  elseif style == 'LowerRoman' then core = roman(n, false)
  elseif style == 'UpperRoman' then core = roman(n, true)
  else core = tostring(n) end
  if delim == 'TwoParens' then return '(' .. core .. ')'
  elseif delim == 'OneParen' then return core .. ')'
  else return core .. '.' end
end

local function prepend_inlines(block, inlines)
  if block.t == 'Para' or block.t == 'Plain' then
    local new = pandoc.List(inlines)
    new:extend(block.content)
    return pandoc.Para(new)
  end
  local para = pandoc.Para(inlines)
  return { para, block }
end

function OrderedList(el)
  local style = el.listAttributes.style or 'Decimal'
  local delim = el.listAttributes.delimiter or 'Period'
  local start = el.listAttributes.start or 1
  -- start=N marker planted by tex2md.py in the first item
  local first = el.content[1] and el.content[1][1]
  local marked = false
  if first and first.content and first.content[1] and first.content[1].t == 'Str' then
    local n = first.content[1].text:match('^ZZSTART(%d+)ZZ$')
    if n then
      local rest = pandoc.List(first.content)
      rest:remove(1)
      if rest[1] and rest[1].t == 'Space' then rest:remove(1) end
      el.content[1][1] = pandoc.Plain(rest)
      start = tonumber(n)
      marked = true
    end
  end
  if style == 'Decimal' and delim == 'Period' or style == 'DefaultStyle' then
    if marked then
      return pandoc.OrderedList(el.content, pandoc.ListAttributes(start, 'Decimal', 'Period'))
    end
    return nil -- keep as a real Markdown list
  end
  local out = pandoc.List()
  local n = start
  for _, item in ipairs(el.content) do
    local lab = pandoc.Strong({ pandoc.Str(label_for(n, style, delim)) })
    local firstblk = true
    for _, blk in ipairs(item) do
      if firstblk then
        local res = prepend_inlines(blk, { lab, pandoc.Space() })
        if res.t then out:insert(res) else out:extend(res) end
        firstblk = false
      else
        out:insert(blk)
      end
    end
    n = n + 1
  end
  return out
end

function DefinitionList(el)
  local out = pandoc.List()
  for _, item in ipairs(el.content) do
    local term, defs = item[1], item[2]
    local lab = pandoc.Strong(term)
    local first = true
    for _, def in ipairs(defs) do
      for _, blk in ipairs(def) do
        if first then
          local res = prepend_inlines(blk, { lab, pandoc.Space() })
          if res.t then out:insert(res) else out:extend(res) end
          first = false
        else
          out:insert(blk)
        end
      end
    end
    if first then out:insert(pandoc.Para({ lab })) end
  end
  return out
end

function Div(el)
  if el.classes:includes('proof') then
    local last = el.content[#el.content]
    if last and (last.t == 'Para' or last.t == 'Plain') then
      last.content:insert(pandoc.Space())
      last.content:insert(pandoc.Str('\u{220E}'))
    end
  end
  return el.content
end

local function split_display(block)
  local out = pandoc.List()
  local cur = pandoc.List()
  local function flush()
    -- drop segments that are only whitespace / line breaks
    local keep = false
    for _, i in ipairs(cur) do
      if i.t ~= 'Space' and i.t ~= 'SoftBreak' and i.t ~= 'LineBreak' then keep = true end
    end
    if keep then out:insert(pandoc.Para(cur)) end
    cur = pandoc.List()
  end
  for _, i in ipairs(block.content) do
    if i.t == 'Math' and i.mathtype == 'DisplayMath' then
      flush()
      out:insert(pandoc.Para({ i }))
    else
      cur:insert(i)
    end
  end
  flush()
  return out
end

function Para(el)
  for _, i in ipairs(el.content) do
    if i.t == 'Math' and i.mathtype == 'DisplayMath' then return split_display(el) end
  end
  return nil
end

function Plain(el)
  for _, i in ipairs(el.content) do
    if i.t == 'Math' and i.mathtype == 'DisplayMath' then return split_display(el) end
  end
  return nil
end

-- Python-Markdown does not understand pandoc's backslash-newline; emit an explicit <br>.
function LineBreak()
  return pandoc.RawInline('html', '<br>')
end
