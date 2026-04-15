const { SlashCommandBuilder } = require('discord.js');

module.exports = {
    owner: true,
    data: new SlashCommandBuilder()
        .setName('animatedav')
        .setDescription('Set the avatar to an animated image')
        .addStringOption(option =>
            option.setName('avatar')
                .setDescription('The Avatar to animate').setRequired(true)),
    async execute(interaction, client) {
        const { options } = interaction;
        const avatar = options.getAttachments('avatar');

        async function sendMessage(message) {
            const embed = new EmbedBuilder()
                .setDescription(message)
                .setColor('Random');
            await interaction.reply({ embeds: [embed], ephemeral: true });
        }

        if (avatar.contentType !== 'image/gif') return await sendMessage('Error: The provided avatar must be an animated image (GIF).');

        var error;
        await client.user.setAvatar(avatar.url).catch(async err => {
            error = true;
            console.log(err);
            return await sendMessage('Error: \'${err.toString()}\'');
        });

        if (error) return;
        await sendMessage('Avatar updated successfully!');
    }
}   