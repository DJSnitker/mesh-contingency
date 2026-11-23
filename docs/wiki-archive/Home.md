<p align="center">
  <img src="https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/images/mesh-contingency-lockup-dark-2x.png" alt="Mesh Contingency" width="560">
</p>

<p align="center">
  <strong>A contingency link over MeshCore.</strong><br>
  Weather, check-ins, private messages and email, from nothing but a mesh radio.
</p>

---

Send the node a **direct message** from any [MeshCore](https://github.com/meshcore-dev/MeshCore)
radio and it replies over the mesh. With only a mesh radio you can check the
weather, read a Bible verse, check in so others know you're ok, leave messages
for other users (sealed with a passphrase if you like), or get a message out
by email.

## Start here

| | Guide | What's in it |
|---|---|---|
| 🧰 | **[Set Up a Node](Set-Up-a-Node)** | Installing a node on Linux with one command, making yourself its first admin, and its first settings; then [running it as a systemd service](Running-as-a-systemd-Service-on-Linux): starting at boot, restarting itself, reading its log, updating |
| 📱 | **[User App Guide](User-App-Guide)** | The users' app for phones and computers: installing it, connecting your radio, and every screen |
| 📻 | **[User Guide](User-Guide)** | Getting connected, joining, checking in, leaving messages, keeping them private, sending email, all by typing commands |
| 🛡️ | **[Admin Guide](Admin-Guide)** | Adding and managing users, checking the node's health, being told about problems, history and backups, adverts, weather alerts, news and roll calls, the web console, on the node or from other computers, fixing problems |
| 📖 | **[Commands (A–Z)](Commands)** | Every command with its usage, who can use it and examples |

## Try it

From your MeshCore app, send the node a direct message:

```
help
→ commands: help, wx, verse, ok, status, join. Send help <command> for usage
```

No answer? Your radio and the node need to have heard each other's advert
first; see [Get connected](User-Guide#get-connected).

---

How the software fits together (the bot, the web console, the phone and
desktop app, and where each lives in the repository) is in the
**[software architecture deck](https://raw.githubusercontent.com/wiki/DJSnitker/mesh-contingency/files/mesh-contingency-architecture.pptx)**
(PowerPoint, as of 0.11.0).

Setting up your own node is covered in the project's
[README](https://github.com/DJSnitker/mesh-contingency#readme).
