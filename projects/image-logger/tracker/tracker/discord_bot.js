/**
 * bot/discord_bot.js
 *
 * Cliente Discord que responde a /track:
 *  - Llama al endpoint /convert del tracker (PUBLIC_BASE + /convert)
 *  - Añade header x-hook-token con HOOK_TOKEN para autenticación
 *  - Responde al usuario con la URL generada
 *
 * Requisitos previos:
 *  - .env con DISCORD_BOT_TOKEN, PUBLIC_BASE, HOOK_TOKEN (y opcionalmente DISCORD_GUILD_ID/DISCORD_APP_ID)
 *  - Instalar dependencias:
 *      npm install discord.js node-fetch dotenv
 *
 * Ejecutar:
 *  node bot/discord_bot.js
 *
 * Nota importante:
 *  - No ejecutes dos procesos simultáneos con el mismo bot token (evita múltiples clientes conectados al mismo tiempo).
 */

const { Client, GatewayIntentBits } = require('discord.js');
const fetch = require('node-fetch');
require('dotenv').config();

const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
const PUBLIC_BASE = (process.env.PUBLIC_BASE || 'http://localhost:5000').replace(/\/$/, '');
const HOOK_TOKEN = process.env.HOOK_TOKEN;

if (!BOT_TOKEN) {
  console.error('DISCORD_BOT_TOKEN no configurado en .env');
  process.exit(1);
}

const client = new Client({
  intents: [GatewayIntentBits.Guilds]
});

client.once('ready', () => {
  console.log(`Bot listo. Conectado como ${client.user.tag}`);
});

client.on('interactionCreate', async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  if (interaction.commandName === 'track') {
    await interaction.deferReply({ ephemeral: true });

    const url = interaction.options.getString('url', true);
    const identifier = interaction.options.getString('identifier', false) || null;
    const prefer = interaction.options.getString('prefer', false) || 'auto';
    const name = interaction.options.getString('name', false) || null;

    const payload = {
      url,
      prefer,
      identifier,
      name
    };

    const convertUrl = `${PUBLIC_BASE}/convert`;

    try {
      const resp = await fetch(convertUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(HOOK_TOKEN ? { 'x-hook-token': HOOK_TOKEN } : {})
        },
        body: JSON.stringify(payload),
        timeout: 10000
      });

      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        console.error('Error /convert:', resp.status, text);
        await interaction.editReply({ content: `Error del tracker (${resp.status}). Revisa logs.` });
        return;
      }

      const body = await resp.json().catch(() => null);
      if (!body) {
        await interaction.editReply({ content: 'Respuesta inesperada del tracker.' });
        return;
      }

      if (body.mode === 'append') {
        const out = body.appended_url || url;
        await interaction.editReply({ content: `Modo append — usa esta URL:\n${out}` });
      } else if (body.mode === 'redirect') {
        const short = body.short_url || `${PUBLIC_BASE}/r/${body.slug || ''}`;
        await interaction.editReply({ content: `Short URL creada:\n${short}` });
      } else {
        await interaction.editReply({ content: `Respuesta del tracker: ${JSON.stringify(body)}` });
      }
    } catch (err) {
      console.error('Excepción llamando a /convert:', err);
      await interaction.editReply({ content: `Error comunicando con el tracker: ${err.message}` });
    }
  }
});

client.login(BOT_TOKEN).catch(err => {
  console.error('Fallo al iniciar sesión del bot:', err);
  process.exit(1);
});