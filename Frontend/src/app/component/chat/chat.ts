import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { Chat as C } from '../../service/chat';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.html',
})
export class Chat {
  userInput = '';
  messages: { role: string; text: string }[] = [];

  constructor(private chatService: C) {}

  botText = '';

async send() {

  if (!this.userInput?.trim()) return;

  const userMsg = this.userInput;
  this.messages.push({ role: 'user', text: userMsg });

  this.userInput = '';

  const botReply = await this.chatService.sendMessage(userMsg);

  console.log("BOT:", botReply);   // DEBUG

  this.messages.push({ role: 'bot', text: botReply });
}
}
