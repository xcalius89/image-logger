/**
 * bot/register_commands.js
 *
 * Registra el comando slash `/track` en Discord (guild o global según config).
 *
 * Requisitos:
 *  - Crear .env con DISCORD_APP_ID, DISCORD_BOT_TOKEN y opcionalmente DISCORD_GUILD_ID
 *  - Instalar dependencias:
 *      npm init -y
 *      npm install discord.js dotenv
 *
 * Uso:
 *  - Para registro en un guild (rápido, cambios inmediatos): establece DISCORD_GUILD_ID en .env y ejecuta:
 *      node bot/register_commands.js
 *  - Para registro global (puede tardar hasta 1 hora en propagarse): borra/omite DISCORD_GUILD_ID y ejecuta:
 *      node bot/register_commands.js
 */

const { REST, Routes, SlashCommandBuilder } = require('discord.js');
require('dotenv').config();

const APP_ID = process.env.DISCORD_APP_ID;
const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
const GUILD_ID = process.env.DISCORD_GUILD_ID; // opcional: para pruebas rápidas en un guild

if (!APP_ID || !BOT_TOKEN) {
  console.error('Falta DISCORD_APP_ID o DISCORD_BOT_TOKEN en .env');
  process.exit(1);
}

const trackCommand = new SlashCommandBuilder()
  .setName('track')
  .setDescription('Crear un tracked link (append o redirect).')
  .addStringOption(opt =>
    opt.setName('url')
      .setDescription('URL destino a trackear')
      .setRequired(true))
  .addStringOption(opt =>
    opt.setName('identifier')
      .setDescription('Identificador (username/email/alias) para que Sherlock busque (opcional)')
      .setRequired(false))
  .addStringOption(opt =>
    opt.setName('prefer')
      .setDescription('Preferencia: auto/append/redirect')
      .setRequired(false)
      .addChoices(
        { name: 'auto', value: 'auto' },
        { name: 'append', value: 'append' },
        { name: 'redirect', value: 'redirect' }
      ))
  .addStringOption(opt =>
    opt.setName('name')
      .setDescription('Nombre/etiqueta para este recurso (opcional)')
      .setRequired(false));

const commands = [
  trackCommand.toJSON()
];

const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);

(async () => {
  try {
    console.log('Registering slash commands...');
    if (GUILD_ID) {
      const data = await rest.put(
        Routes.applicationGuildCommands(APP_ID, GUILD_ID),
        { body: commands }
      );
      console.log(`Registered ${data.length} commands to guild ${GUILD_ID}`);
    } else {
      const data = await rest.put(
        Routes.applicationCommands(APP_ID),
        { body: commands }
      );
      console.log(`Registered ${data.length} global commands (may take up to 1 hour)`);
    }
  } catch (err) {
    console.error('Error registering commands:', err);
    process.exit(1);
  }
})();