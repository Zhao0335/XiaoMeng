use std::io::{self, BufRead, Write};
use std::sync::Arc;
use tokio::sync::RwLock;
use anyhow::Result;

use crate::models::{Message, Response, Source, User};
use crate::gateway::{BaseGateway, MessageHandler};

pub struct CliGateway {
    running: Arc<RwLock<bool>>,
    message_handler: Arc<RwLock<Option<MessageHandler>>>,
    user: User,
}

impl CliGateway {
    pub fn new(user_id: impl Into<String>) -> Self {
        Self {
            running: Arc::new(RwLock::new(false)),
            message_handler: Arc::new(RwLock::new(None)),
            user: User::owner(user_id),
        }
    }

    pub async fn run_interactive(&mut self) -> Result<()> {
        *self.running.write().await = true;
        
        println!("🦀 XiaoMengCore CLI Gateway");
        println!("Type '/exit' to quit\n");

        let stdin = io::stdin();
        let mut stdout = io::stdout();

        print!("你: ");
        stdout.flush()?;

        for line in stdin.lock().lines() {
            if !*self.running.read().await {
                break;
            }

            match line {
                Ok(input) => {
                    if input.trim() == "/exit" {
                        println!("再见！");
                        break;
                    }

                    if input.trim().is_empty() {
                        print!("你: ");
                        stdout.flush()?;
                        continue;
                    }

                    let message = Message::cli(self.user.clone(), input);

                    let handler = self.message_handler.read().await;
                    if let Some(handler) = handler.as_ref() {
                        match handler(message).await {
                            Ok(response) => {
                                println!("小螃蟹: {}", response.content);
                            }
                            Err(e) => {
                                eprintln!("错误: {}", e);
                            }
                        }
                    } else {
                        println!("小螃蟹: (没有配置消息处理器)");
                    }

                    print!("\n你: ");
                    stdout.flush()?;
                }
                Err(e) => {
                    eprintln!("读取输入错误: {}", e);
                    break;
                }
            }
        }

        *self.running.write().await = false;
        Ok(())
    }
}

#[async_trait::async_trait]
impl BaseGateway for CliGateway {
    fn source(&self) -> Source {
        Source::Cli
    }

    async fn start(&mut self) -> Result<()> {
        *self.running.write().await = true;
        Ok(())
    }

    async fn stop(&mut self) -> Result<()> {
        *self.running.write().await = false;
        Ok(())
    }

    async fn send_message(&self, response: Response) -> Result<()> {
        println!("{}", response.content);
        Ok(())
    }

    fn is_running(&self) -> bool {
        futures::executor::block_on(async {
            *self.running.read().await
        })
    }

    fn set_message_handler(&mut self, handler: MessageHandler) {
        futures::executor::block_on(async {
            let mut h = self.message_handler.write().await;
            *h = Some(handler);
        });
    }
}
