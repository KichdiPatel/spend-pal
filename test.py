# def reconcile():
#     transactions = NewTx.query.all()
#     user = User.query.first()

#     if not transactions or not user:
#         return jsonify({"status": "No transactions or user not found"}), 404

#     user.currentlyReconciling = True
#     db.session.add(user)
#     db.session.commit()

#     for tx in transactions:
#         message = (
#             f"Transaction: {tx.name}\n"
#             f"Amount: {tx.amount}\n"
#             f"Category: {tx.category}\n"
#             f"Date: {tx.date.strftime('%Y-%m-%d')}\n\n"
#             "Reply with the transaction name and new details (amount, category) if you want to adjust, "
#             "or just reply 'approve' to approve this transaction."
#         )
#         sendText(message)
#         # # user.needsReconcile = False
#         # db.session.add(user)
#         # db.session.commit()

#         time.sleep(10)  # Wait for user response

#         incoming_msg = request.values.get("Body", "").strip()

#         if incoming_msg.lower() == "approve":
#             approved_tx = ApprovedTxs(
#                 name=tx.name,
#                 amount=tx.amount,
#                 category=tx.category,
#                 category_id=tx.category_id,
#                 date=tx.date,
#             )
#             db.session.add(approved_tx)
#             db.session.commit()
#             NewTx.query.filter_by(id=tx.id).delete()
#             db.session.commit()
#         else:
#             parts = incoming_msg.split(",")
#             if len(parts) == 3:
#                 tx_amount, tx_category = parts
#                 tx.amount = float(tx_amount.strip())
#                 tx.category = tx_category.strip()
#                 db.session.add(tx)
#                 db.session.commit()

#                 approved_tx = ApprovedTxs(
#                     name=tx.name,
#                     amount=tx.amount,
#                     category=tx.category,
#                     category_id=tx.category_id,
#                     date=tx.date,
#                 )
#                 db.session.add(approved_tx)
#                 db.session.commit()
#                 NewTx.query.filter_by(id=tx.id).delete()
#                 db.session.commit()

#     user.needsReconcile = False
#     user.currentlyReconciling = False
#     db.session.add(user)
#     db.session.commit()
#     return jsonify({"status": "Reconciliation completed"}), 200


# @app.route("/sms", methods=["GET", "POST"])
# def sms_reply():
#     user = User.query.first()
#     if not user.currentlyReconciling:
#         incoming_msg = request.values.get("Body", "").strip()

#         # Create a response object
#         resp = MessagingResponse()

#         if incoming_msg.lower() == "budget" and user.needsReconcile == False:
#             budget = getBudget()
#             resp.message(budget)

#         elif incoming_msg.lower() == "reconcile" and user.needsReconcile == True:
#             reconcile()

#         elif incoming_msg.lower() != "reconcile" and user.needsReconcile == True:
#             resp.message(
#                 "Please type 'reconcile' to begin reconciling. No other actions can take place until you reconcile your transactions."
#             )

#         elif incoming_msg.lower() != "budget" and user.needsReconcile == False:
#             resp.message(
#                 "Currently the only available command is 'budget' to retreive your current budget scenario"
#             )

#         return str(resp)
#     else:
#         return ""
