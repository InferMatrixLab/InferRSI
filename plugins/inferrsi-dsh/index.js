import { readFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import remoteHost from './remote-host.cjs'

export const name = 'inferrsi-dsh'
export const inject = ['skills']

function registerSkill(ctx, name) {
  const path = fileURLToPath(new URL(`./assets/${name}/SKILL.md`, import.meta.url))
  const skill = readFileSync(path, 'utf8')
  const frontmatter = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/u.exec(skill)
  const description = frontmatter?.[1].match(/^description:[ \t]+([^\r\n]+)/mu)?.[1].trim()
  const content = frontmatter && skill.slice(frontmatter[0].length)
  if (!description || !content?.trim()) {
    throw new Error(`The bundled ${name} skill requires a description and instructions.`)
  }
  ctx.skills.register({
    name,
    description,
    content,
    source: 'runtime',
    path,
    resourceBase: { kind: 'directory', path: dirname(path) },
  })
}

export function apply(ctx) {
  registerSkill(ctx, 'inferrsi')
  registerSkill(ctx, 'inferrsi-feedback')
  ctx.inject(['connection', 'tools'], bridge => {
    remoteHost.installRemote(bridge, fileURLToPath(new URL('./runtime/', import.meta.url)))
  })
}
